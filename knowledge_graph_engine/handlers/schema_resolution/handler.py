# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from graphene import ResolveInfo
from neo4j_graphrag.experimental.components.schema import GraphSchema

try:
    import nest_asyncio
except ImportError:  # pragma: no cover
    nest_asyncio = None

if nest_asyncio is not None:  # pragma: no branch
    nest_asyncio.apply()

from ..telemetry import measure_handler_duration

# Schema imports done lazily inside methods to avoid circular imports at module level
# from neo4j_graphrag.experimental.components.schema import (...)


class SchemaResolverError(Exception):
    """Base error for schema resolution handler."""

    code = "system_error"


logger = logging.getLogger(__name__)


def _suppress_event_loop_closed(loop, context):
    """Suppress 'Event loop is closed' errors from httpx AsyncClient cleanup."""
    exception = context.get("exception")
    if isinstance(exception, RuntimeError) and "Event loop is closed" in str(exception):
        return  # Silently ignore httpx cleanup noise
    loop.default_exception_handler(context)


def _run_async(coro):
    """Run an async coroutine safely from sync context, even inside a running event loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.set_exception_handler(_suppress_event_loop_closed)
    return loop.run_until_complete(coro)


class SchemaResolver:
    """
    Resolves graph schema for extraction and evolves it post-extraction.

    Resolution (before extraction):
    1. graph_schema dict provided → save as new active, use it
    2. graph_schema string ("EXTRACTED"/"FREE"/"FROM_GRAPH") → pass to pipeline
    3. Active schema exists → use it as-is
    4. No active schema → fall back to "EXTRACTED" (let pipeline decide)

    Evolution (after extraction):
    - Read actual labels/types from the graph via SchemaFromExistingGraphExtractor
    - Compare against the active schema definition
    - If new types found → build new version on top of the old one
    - New version is always a superset of the previous version
    """

    def __init__(self, graph_rag_util, partition_key: str, info: Any = None):
        self.graph_rag_util = graph_rag_util
        self.partition_key = partition_key
        self.info = info

    def resolve(
        self,
        text: str,
        graph_schema: Union["GraphSchema", dict, str, None] = None,
    ) -> Union["GraphSchema", str]:
        """
        Returns a value suitable for SimpleKGPipeline's `schema` parameter.

        When an active schema exists, uses a two-phase check:
        - Phase 1 (free): check if any schema node labels appear in the text.
          If yes, the schema likely covers this record → use it as-is.
        - Phase 2 (LLM): if no labels match, ask the LLM to discover what types
          the text needs. If new types found, merge them ON TOP of the active
          schema (new version is always a superset). If no new types, reuse active.
        """

        if isinstance(graph_schema, dict):
            if graph_schema.get("auto_extend"):
                base = self._dict_to_graph_schema(graph_schema)
                merged = self._hybrid_schema(text, base)
                self._save_as_active(merged, "auto")
                return merged
            gs = self._dict_to_graph_schema(graph_schema)
            self._save_as_active(gs, "user")
            return gs

        if isinstance(graph_schema, str):
            if graph_schema == "FROM_GRAPH":
                return self._extract_from_existing_graph()
            if graph_schema == "EXTRACTED" or graph_schema == "FREE":
                return graph_schema
            raise ValueError(f"Unknown schema string: {graph_schema}")

        # No graph_schema provided: use active schema with coverage check
        active = self._load_active_schema()
        if active:
            return self._check_and_evolve(text, active)

        # No active schema exists — let SimpleKGPipeline extract freely.
        # evolve_schema_from_graph() will capture the schema after extraction.
        logger.info(
            "No active schema for partition %s — using EXTRACTED mode. "
            "Schema will be captured from the graph after extraction.",
            self.partition_key,
        )
        return "EXTRACTED"

    def _check_and_evolve(self, text: str, active: "GraphSchema") -> "GraphSchema":
        """
        Two-phase schema coverage check.

        Phase 1 (free, no LLM): Check if any of the active schema's node labels
        appear in the text. If at least one matches, the schema likely covers this
        record — return it as-is.

        Phase 2 (LLM call): If no labels match, the text may contain entity types
        the schema doesn't know about. Ask the LLM to discover types from the text.
        If new types found, merge them ON TOP of the active schema and save a new
        version. The new version is always a superset of the old one.
        """
        # Phase 1: cheap text-based check
        node_labels = self._get_node_labels(active)
        text_lower = text.lower()

        matched = {label for label in node_labels if label.lower() in text_lower}

        if matched:
            logger.debug(
                "Active schema covers text for partition %s (matched: %s) — reusing.",
                self.partition_key,
                ", ".join(sorted(matched)),
            )
            return active

        # Phase 2: no label matched — ask LLM
        logger.info(
            "No schema labels matched text for partition %s — using LLM to check coverage.",
            self.partition_key,
        )
        try:
            discovered = self._discover_schema(text)
        except Exception as e:
            logger.warning(
                "LLM schema discovery failed for partition %s: %s — reusing active schema.",
                self.partition_key,
                e,
            )
            return active

        new_nodes, new_rels, new_patterns = self._find_new_types(active, discovered)

        if not new_nodes and not new_rels and not new_patterns:
            logger.debug(
                "LLM confirmed active schema covers text for partition %s — no evolution needed.",
                self.partition_key,
            )
            return active

        # Build new version on top of the old one (superset)
        merged = self._merge_schemas(active, discovered)
        self._save_as_active(merged, "evolved")
        logger.info(
            "Schema evolved for partition %s: +%d node types, +%d relationship types, +%d patterns. "
            "New version saved as active (superset of previous).",
            self.partition_key,
            len(new_nodes),
            len(new_rels),
            len(new_patterns),
        )
        return merged

    def evolve_schema_from_graph(self, text: str = None) -> None:
        """
        Called after extraction. Reads the actual schema from the graph
        and compares against the active schema definition.

        - If no active schema → save the graph schema as the first active version.
        - If active schema exists but graph has new types → build new version
          on top of the old one (superset).
        - If active schema already covers everything → no-op.

        Falls back to LLM-based schema discovery when APOC is not available
        (requires `text` to be provided).
        """
        # Read what's actually in the graph
        graph_schema = None
        try:
            graph_schema = self._extract_from_existing_graph()
        except Exception as e:
            logger.warning(
                "Could not read schema from graph for partition %s: %s. "
                "Falling back to LLM-based schema discovery.",
                self.partition_key,
                e,
            )

        # Fallback: use LLM to discover schema from the extracted text
        if not graph_schema and text:
            try:
                graph_schema = self._discover_schema(text)
            except Exception as e:
                logger.warning(
                    "LLM schema discovery also failed for partition %s: %s",
                    self.partition_key,
                    e,
                )

        if not graph_schema:
            logger.debug("No schema extracted from graph — skipping evolution.")
            return

        active = self._load_active_schema()

        if not active:
            # First time: save graph schema as the initial active version
            self._save_as_active(graph_schema, "captured")
            logger.info(
                "Captured initial schema from graph for partition %s — saved as active.",
                self.partition_key,
            )
            return

        # Compare: does the active schema already cover what's in the graph?
        new_nodes, new_rels, new_patterns = self._find_new_types(active, graph_schema)

        if not new_nodes and not new_rels and not new_patterns:
            logger.debug(
                "Active schema already covers graph for partition %s — no evolution needed.",
                self.partition_key,
            )
            return

        # Build new version on top of the old one
        merged = self._merge_schemas(active, graph_schema)
        self._save_as_active(merged, "evolved")
        logger.info(
            "Schema evolved for partition %s: +%d node types, +%d relationship types, +%d patterns. "
            "New version saved as active (superset of previous).",
            self.partition_key,
            len(new_nodes),
            len(new_rels),
            len(new_patterns),
        )

    def _load_active_schema(self) -> Optional["GraphSchema"]:
        """Load the active GraphSchema for this partition."""
        from neo4j_graphrag.experimental.components.schema import GraphSchema
        from ...models.repositories import get_repo

        try:
            repo = get_repo("graph_schema")
            record = repo.resolve_active(self.partition_key)
            if record and record.get("schema_definition"):
                raw = record["schema_definition"]
                if isinstance(raw, dict):
                    return GraphSchema.model_validate(raw)
        except Exception as e:
            logger.warning(
                "Failed to load active schema for partition %s: %s",
                self.partition_key,
                e,
            )
        return None

    def _extract_from_existing_graph(self) -> "GraphSchema":
        """Use SchemaFromExistingGraphExtractor to read schema from tenant's Neo4j."""
        from neo4j_graphrag.experimental.components.schema import (
            SchemaFromExistingGraphExtractor,
        )

        extractor = SchemaFromExistingGraphExtractor(
            driver=self.graph_rag_util.driver,
            neo4j_database=self.graph_rag_util.neo4j_database,
        )
        return _run_async(extractor.run())

    def _discover_schema(self, text: str) -> "GraphSchema":
        """Use LLM to discover entity types from text."""
        from neo4j_graphrag.experimental.components.schema import (
            SchemaFromTextExtractor,
        )

        extractor = SchemaFromTextExtractor(llm=self.graph_rag_util.llm)
        return _run_async(extractor.run(text=text))

    def _get_node_labels(self, schema: "GraphSchema") -> Set[str]:
        """Extract all node labels from a schema."""
        labels = set()
        if schema.node_types:
            for nt in schema.node_types:
                if isinstance(nt, str):
                    labels.add(nt)
                else:
                    labels.add(nt.label)
        return labels

    def _get_rel_labels(self, schema: "GraphSchema") -> Set[str]:
        """Extract all relationship labels from a schema."""
        labels = set()
        if schema.relationship_types:
            for rt in schema.relationship_types:
                if isinstance(rt, str):
                    labels.add(rt)
                else:
                    labels.add(rt.label)
        return labels

    def _find_new_types(
        self, active: "GraphSchema", discovered: "GraphSchema"
    ) -> Tuple[List, List, List]:
        """
        Compare discovered schema against active schema.
        Returns (new_node_types, new_rel_types, new_patterns) not in the active schema.
        """
        active_node_labels = self._get_node_labels(active)
        active_rel_labels = self._get_rel_labels(active)
        active_patterns = set()
        if active.patterns:
            for p in active.patterns:
                active_patterns.add(tuple(p) if not isinstance(p, tuple) else p)

        new_nodes = []
        if discovered.node_types:
            for nt in discovered.node_types:
                label = nt if isinstance(nt, str) else nt.label
                if label not in active_node_labels:
                    new_nodes.append(nt)

        new_rels = []
        if discovered.relationship_types:
            for rt in discovered.relationship_types:
                label = rt if isinstance(rt, str) else rt.label
                if label not in active_rel_labels:
                    new_rels.append(rt)

        new_patterns = []
        if discovered.patterns:
            for p in discovered.patterns:
                pt = tuple(p) if not isinstance(p, tuple) else p
                if pt not in active_patterns:
                    new_patterns.append(p)

        return new_nodes, new_rels, new_patterns

    def _auto_generate_and_save(self, text: str) -> "GraphSchema":
        """Use SchemaFromTextExtractor to auto-generate GraphSchema from text, save as active."""
        schema = self._discover_schema(text)
        self._save_as_active(schema, "auto")
        return schema

    def _dict_to_graph_schema(self, schema_dict: dict) -> "GraphSchema":
        """
        Convert user-provided dict (from GraphQL JSON input) to GraphSchema.
        Accepts neo4j-graphrag-python format:
          { "node_types": [...], "relationship_types": [...], "patterns": [...] }
        """
        from neo4j_graphrag.experimental.components.schema import (
            ConstraintType,
            GraphSchema,
            NodeType,
            PropertyType,
            RelationshipType,
            SchemaBuilder,
        )

        node_types = []
        for nt in schema_dict.get("node_types", []):
            if isinstance(nt, str):
                node_types.append(nt)
            else:
                props = [PropertyType(**p) for p in nt.get("properties", [])]
                node_types.append(
                    NodeType(
                        label=nt["label"],
                        description=nt.get("description", ""),
                        properties=(
                            props
                            if props
                            else [PropertyType(name="name", type="STRING")]
                        ),
                    )
                )

        rel_types = []
        for rt in schema_dict.get("relationship_types", []):
            if isinstance(rt, str):
                rel_types.append(rt)
            else:
                props = [PropertyType(**p) for p in rt.get("properties", [])]
                rel_types.append(
                    RelationshipType(
                        label=rt["label"],
                        description=rt.get("description", ""),
                        properties=props,
                    )
                )

        patterns = []
        for p in schema_dict.get("patterns", []):
            if isinstance(p, (list, tuple)):
                patterns.append((p[0], p[1], p[2]))
            elif isinstance(p, dict):
                patterns.append((p["source"], p["relationship"], p["target"]))
            else:
                patterns.append(p)

        constraints = []
        for c in schema_dict.get("constraints", []):
            constraints.append(ConstraintType(**c))

        return SchemaBuilder.create_schema_model(
            node_types=node_types,
            relationship_types=rel_types if rel_types else None,
            patterns=patterns if patterns else None,
            constraints=constraints if constraints else None,
        )

    def _hybrid_schema(self, text: str, base_schema: "GraphSchema") -> "GraphSchema":
        """Start from base schema, LLM discovers additional types from text."""
        auto_schema = self._discover_schema(text)
        return self._merge_schemas(base_schema, auto_schema)

    def _merge_schemas(self, base: "GraphSchema", auto: "GraphSchema") -> "GraphSchema":
        """Merge base and auto schemas. Base takes priority. Result is always a superset of base."""
        from neo4j_graphrag.experimental.components.schema import SchemaBuilder

        base_labels = self._get_node_labels(base)
        base_rel_labels = self._get_rel_labels(base)

        merged_nodes = list(base.node_types) if base.node_types else []
        if auto.node_types:
            for nt in auto.node_types:
                label = nt if isinstance(nt, str) else nt.label
                if label not in base_labels:
                    merged_nodes.append(nt)

        merged_rels = list(base.relationship_types) if base.relationship_types else []
        if auto.relationship_types:
            for rt in auto.relationship_types:
                label = rt if isinstance(rt, str) else rt.label
                if label not in base_rel_labels:
                    merged_rels.append(rt)

        merged_patterns = list(base.patterns) if base.patterns else []
        if auto.patterns:
            for p in auto.patterns:
                if p not in merged_patterns:
                    merged_patterns.append(p)

        return SchemaBuilder.create_schema_model(
            node_types=merged_nodes,
            relationship_types=merged_rels if merged_rels else None,
            patterns=merged_patterns if merged_patterns else None,
            constraints=list(base.constraints) if base.constraints else None,
        )

    @staticmethod
    def _sanitize_for_dynamodb(obj):
        """Recursively convert tuples to lists for DynamoDB serialization."""
        if isinstance(obj, dict):
            return {k: SchemaResolver._sanitize_for_dynamodb(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [SchemaResolver._sanitize_for_dynamodb(i) for i in obj]
        return obj

    def _save_as_active(self, schema: "GraphSchema", schema_type: str):
        """Save schema as the new active schema, deactivating any existing active one."""
        import pendulum
        from neo4j_graphrag.experimental.components.schema import GraphSchema
        from ...models.repositories import get_repo

        now = pendulum.now("UTC")
        neo4j_schema_string = self._build_neo4j_schema_string(schema)
        definition = self._sanitize_for_dynamodb(schema.model_dump())
        schema_name = f"{schema_type}_{now.format('YYYYMMDDHHmmss')}"

        # Use the repository boundary to create the new active schema.
        # The repository's insert_update handles the single-active invariant
        # (deactivating other active schemas) on both backends.
        repo = get_repo("graph_schema")
        repo.insert_update(
            self.info,
            partition_key=self.partition_key,
            schema_name=schema_name,
            schema_type=schema_type,
            schema_definition=definition,
            neo4j_schema_string=neo4j_schema_string,
            status="active",
            created_at=now,
            updated_at=now,
        )

    def _build_neo4j_schema_string(self, schema: "GraphSchema") -> str:
        """
        Convert GraphSchema to plain-text description string
        used by Text2CypherRetriever for Cypher generation.
        """
        lines = []
        if schema.node_types:
            for nt in schema.node_types:
                if isinstance(nt, str):
                    lines.append(f"(:{nt})")
                else:
                    props = (
                        ", ".join(p.name for p in nt.properties)
                        if nt.properties
                        else ""
                    )
                    lines.append(f"(:{nt.label} {{{props}}})")
        if schema.patterns:
            for p in schema.patterns:
                # Patterns are tuples: (source, relationship, target)
                lines.append(f"(:{p[0]})-[:{p[1]}]->(:{p[2]})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public dispatch functions
# ---------------------------------------------------------------------------


def _resolve_schema(info: ResolveInfo, **kwargs: Any) -> Dict[str, Any]:
    """Private implementation — resolve schema for extraction."""
    from ..config import Config

    partition_key = kwargs.get("partition_key")
    if not partition_key:
        raise ValueError("partition_key is required")

    graph_rag_util = Config.get_graph_rag_util(partition_key)
    resolver = SchemaResolver(graph_rag_util, partition_key, info)
    result = resolver.resolve(
        text=kwargs.get("text", ""),
        graph_schema=kwargs.get("graph_schema"),
    )

    # Convert GraphSchema to dict for serialization
    if hasattr(result, "model_dump"):
        return {"status": "success", "schema": result.model_dump()}
    return {"status": "success", "schema": result}


def dispatch_resolve_schema(info: ResolveInfo, **kwargs: Any) -> Dict[str, Any]:
    """Public dispatch — wraps _resolve_schema with telemetry."""
    with measure_handler_duration(
        info, operation="resolve_schema", handler="schema_resolution"
    ):
        return _resolve_schema(info, **kwargs)


def _evolve_schema(info: ResolveInfo, **kwargs: Any) -> Dict[str, Any]:
    """Private implementation — evolve schema from graph after extraction."""
    from ..config import Config

    partition_key = kwargs.get("partition_key")
    if not partition_key:
        raise ValueError("partition_key is required")

    graph_rag_util = Config.get_graph_rag_util(partition_key)
    resolver = SchemaResolver(graph_rag_util, partition_key, info)
    resolver.evolve_schema_from_graph(text=kwargs.get("text"))

    return {"status": "success", "partition_key": partition_key}


def dispatch_evolve_schema(info: ResolveInfo, **kwargs: Any) -> Dict[str, Any]:
    """Public dispatch — wraps _evolve_schema with telemetry."""
    with measure_handler_duration(
        info, operation="evolve_schema", handler="schema_resolution"
    ):
        return _evolve_schema(info, **kwargs)
