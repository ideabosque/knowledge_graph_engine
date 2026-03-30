# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import asyncio
import logging
from typing import Dict, List, Optional, Set, Tuple, Union

try:
    import nest_asyncio
except ImportError:  # pragma: no cover
    nest_asyncio = None

if nest_asyncio is not None:  # pragma: no branch
    nest_asyncio.apply()

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

from neo4j_graphrag.experimental.components.schema import (
    GraphSchema,
    NodeType,
    RelationshipType,
    PropertyType,
    ConstraintType,
    SchemaBuilder,
    SchemaFromTextExtractor,
    SchemaFromExistingGraphExtractor,
)


class SchemaResolver:
    """
    Resolves graph schema for a partition with automatic schema evolution.

    Priority order:
    1. graph_schema dict provided → save as new active schema (deactivates old), use it
    2. graph_schema string ("EXTRACTED"/"FREE"/"FROM_GRAPH") → use directly
    3. Active schema exists → verify it covers the text:
       a. If it covers the text → reuse as-is (no save)
       b. If new types discovered → merge into active schema, save as new version
    4. No active schema → auto-generate from text, save as new active schema

    All methods use the exact neo4j-graphrag-python API.
    """

    def __init__(self, graph_rag_util, partition_key: str):
        self.graph_rag_util = graph_rag_util
        self.partition_key = partition_key

    def resolve(
        self,
        text: str,
        graph_schema: Union[GraphSchema, dict, str, None] = None,
    ) -> Union[GraphSchema, str]:
        """
        Returns a value suitable for SimpleKGPipeline's `schema` parameter:
        either a GraphSchema object, or "EXTRACTED"/"FREE" string.

        When no graph_schema is provided, uses the active schema. If the active
        schema doesn't cover the entity types in the text, it evolves the schema
        by merging new types and saving a new version.
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

        # No graph_schema provided: use active schema with evolution check
        active = self._load_active_schema()
        if active:
            return self._verify_and_evolve(text, active)
        return self._auto_generate_and_save(text)

    def _verify_and_evolve(self, text: str, active: GraphSchema) -> GraphSchema:
        """
        Check if the active schema covers the entity types in the text.
        If yes, return the active schema as-is (no save, no LLM cost for most records).
        If new types are discovered, merge them into the active schema and save a new version.
        """
        # Extract what the LLM thinks the text needs
        discovered = self._discover_schema(text)

        # Check coverage
        new_nodes, new_rels, new_patterns = self._find_new_types(active, discovered)

        if not new_nodes and not new_rels and not new_patterns:
            logger.debug(
                "Active schema covers text for partition %s — reusing without save.",
                self.partition_key,
            )
            return active

        # Schema evolution: merge new types into the active schema
        logger.info(
            "Schema evolution for partition %s: +%d node types, +%d relationship types, +%d patterns",
            self.partition_key,
            len(new_nodes),
            len(new_rels),
            len(new_patterns),
        )
        merged = self._merge_schemas(active, discovered)
        self._save_as_active(merged, "evolved")
        return merged

    def _discover_schema(self, text: str) -> GraphSchema:
        """Use LLM to discover entity types from text."""
        extractor = SchemaFromTextExtractor(llm=self.graph_rag_util.llm)
        return _run_async(extractor.run(text=text))

    def _get_node_labels(self, schema: GraphSchema) -> Set[str]:
        """Extract all node labels from a schema."""
        labels = set()
        if schema.node_types:
            for nt in schema.node_types:
                if isinstance(nt, str):
                    labels.add(nt)
                else:
                    labels.add(nt.label)
        return labels

    def _get_rel_labels(self, schema: GraphSchema) -> Set[str]:
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
        self, active: GraphSchema, discovered: GraphSchema
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

    def _load_active_schema(self) -> Optional[GraphSchema]:
        """Load the active GraphSchema for this partition."""
        from ..models.graph_schema import get_active_graph_schema

        try:
            record = get_active_graph_schema(self.partition_key)
            if record and record.schema_definition:
                return GraphSchema.from_dict(dict(record.schema_definition))
        except Exception:
            pass
        return None

    def _auto_generate_and_save(self, text: str) -> GraphSchema:
        """Use SchemaFromTextExtractor to auto-generate GraphSchema from text, save as active."""
        schema = self._discover_schema(text)
        self._save_as_active(schema, "auto")
        return schema

    def _extract_from_existing_graph(self) -> GraphSchema:
        """Use SchemaFromExistingGraphExtractor to read schema from tenant's Neo4j."""
        extractor = SchemaFromExistingGraphExtractor(
            driver=self.graph_rag_util.driver,
            neo4j_database=self.graph_rag_util.neo4j_database,
        )
        return _run_async(extractor.run())

    def _dict_to_graph_schema(self, schema_dict: dict) -> GraphSchema:
        """
        Convert user-provided dict (from GraphQL JSON input) to GraphSchema.
        Accepts neo4j-graphrag-python format:
          { "node_types": [...], "relationship_types": [...], "patterns": [...] }
        """
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
                        properties=props if props else [PropertyType(name="name", type="STRING")],
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

    def _hybrid_schema(self, text: str, base_schema: GraphSchema) -> GraphSchema:
        """Start from base schema, LLM discovers additional types from text."""
        auto_schema = self._discover_schema(text)
        return self._merge_schemas(base_schema, auto_schema)

    def _merge_schemas(self, base: GraphSchema, auto: GraphSchema) -> GraphSchema:
        """Merge base and auto schemas. Base takes priority."""
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

    def _save_as_active(self, schema: GraphSchema, schema_type: str):
        """Save schema as the new active schema, deactivating any existing active one."""
        import pendulum
        from ..models.graph_schema import GraphSchemaModel, _deactivate_current_active_schema

        now = pendulum.now("UTC")
        neo4j_schema_string = self._build_neo4j_schema_string(schema)
        definition = self._sanitize_for_dynamodb(schema.model_dump())
        schema_name = f"{schema_type}_{now.format('YYYYMMDDHHmmss')}"

        # Deactivate the current active schema first
        _deactivate_current_active_schema(self.partition_key)

        GraphSchemaModel(
            self.partition_key,
            schema_name,
            schema_type=schema_type,
            schema_definition=definition,
            neo4j_schema_string=neo4j_schema_string,
            status="active",
            created_at=now,
            updated_at=now,
        ).save()

    def _build_neo4j_schema_string(self, schema: GraphSchema) -> str:
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
                    props = ", ".join(p.name for p in nt.properties) if nt.properties else ""
                    lines.append(f"(:{nt.label} {{{props}}})")
        if schema.patterns:
            for p in schema.patterns:
                # Patterns are tuples: (source, relationship, target)
                lines.append(f"(:{p[0]})-[:{p[1]}]->(:{p[2]})")
        return "\n".join(lines)
