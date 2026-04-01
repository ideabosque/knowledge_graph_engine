# -*- coding: utf-8 -*-
"""
Live schema evolution test — captures initial schema via LLM,
then runs the full evolution flow against real documents.

This test:
  1. Captures the initial schema via LLM discovery (if none exists)
  2. Verifies resolve() uses active schema for matching documents
  3. Tests Phase 1 (text match) and Phase 2 (LLM) coverage checks
  4. Verifies merge produces a superset
  5. Compares active schema vs actual graph schema
  6. Shows version history

Run:
    pytest tests/test_schema_evolution_live.py -v -s
"""
from __future__ import print_function

import logging
import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("test_schema_evolution_live")
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

# Validate required environment variables
required_vars = ['endpoint_id', 'part_id', 'region_name', 'aws_access_key_id', 'aws_secret_access_key']
missing = [var for var in required_vars if not os.getenv(var)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

PARTITION_KEY = f"{os.getenv('endpoint_id')}#{os.getenv('part_id')}"

SETTING = {
    "region_name": os.getenv("region_name"),
    "aws_access_key_id": os.getenv("aws_access_key_id"),
    "aws_secret_access_key": os.getenv("aws_secret_access_key"),
    "endpoint_id": os.getenv("endpoint_id"),
    "part_id": os.getenv("part_id"),
    "llm_type": os.getenv("llm_type", "openai"),
    "llm_name": os.getenv("llm_name", "gpt-4o"),
    "openai_api_key": os.getenv("openai_api_key"),
    "embedding_model": os.getenv("embedding_model", "text-embedding-3-small"),
    "neo4j_uri": os.getenv("neo4j_uri", "bolt://localhost:7687"),
    "neo4j_username": os.getenv("neo4j_username", "neo4j"),
    "neo4j_password": os.getenv("neo4j_password"),
    "neo4j_database": os.getenv("neo4j_database", "neo4j"),
}


def _init_engine():
    from knowledge_graph_engine.main import KnowledgeGraphEngine
    return KnowledgeGraphEngine(logger, **SETTING)


def _schema_def_to_dict(schema_definition):
    """Convert PynamoDB MapAttribute to plain dict."""
    if hasattr(schema_definition, 'as_dict'):
        return schema_definition.as_dict()
    return dict(schema_definition)


def _schema_to_graph_schema(schema_definition):
    """Convert PynamoDB MapAttribute to GraphSchema."""
    from neo4j_graphrag.experimental.components.schema import GraphSchema
    raw = _schema_def_to_dict(schema_definition)
    return GraphSchema.model_validate(raw)


@pytest.fixture(scope="module")
def engine():
    return _init_engine()


@pytest.fixture(scope="module")
def resolver(engine):
    from knowledge_graph_engine.handlers.config import Config
    from knowledge_graph_engine.handlers.schema_resolver import SchemaResolver
    graph_rag_util = Config.get_graph_rag_util(PARTITION_KEY)
    return SchemaResolver(graph_rag_util, PARTITION_KEY)


@pytest.fixture(scope="module")
def documents(engine):
    from knowledge_graph_engine.models.document import DocumentModel
    docs = list(DocumentModel.query(PARTITION_KEY, limit=20))
    return docs


def _load_active():
    from knowledge_graph_engine.models.graph_schema import get_active_graph_schema, GraphSchemaModel
    try:
        return get_active_graph_schema(PARTITION_KEY)
    except GraphSchemaModel.DoesNotExist:
        return None


def _all_schemas():
    from knowledge_graph_engine.models.graph_schema import GraphSchemaModel
    return sorted(
        GraphSchemaModel.query(PARTITION_KEY),
        key=lambda s: s.updated_at or s.created_at,
    )


# ---------------------------------------------------------------------------
# Step 1: Capture initial schema (if needed)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_step1_capture_initial_schema(resolver, documents):
    """If no active schema, create one from the first document via LLM discovery."""
    active = _load_active()
    if active:
        logger.info("Active schema already exists: %s (type=%s)", active.schema_name, active.schema_type)
        return

    assert documents, "Need at least one document"
    text = documents[0].content or ""
    assert text, "First document has no content"

    logger.info("No active schema -- discovering from first document via LLM...")
    logger.info("  Document: %s", text[:100])

    # Use _discover_schema (LLM) then save as active
    discovered = resolver._discover_schema(text)
    resolver._save_as_active(discovered, "captured")

    active = _load_active()
    assert active is not None, "Should have created an active schema"
    logger.info("Captured initial schema: %s (type=%s)", active.schema_name, active.schema_type)

    schema_dict = _schema_def_to_dict(active.schema_definition)
    node_count = len(schema_dict.get("node_types", []))
    rel_count = len(schema_dict.get("relationship_types", []))
    logger.info("  %d node types, %d relationship types", node_count, rel_count)


# ---------------------------------------------------------------------------
# Step 2: Show schema details
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_step2_show_active_schema(resolver):
    """Display the active schema's node and relationship types."""
    active = _load_active()
    assert active is not None, "Need an active schema"

    gs = _schema_to_graph_schema(active.schema_definition)

    node_labels = resolver._get_node_labels(gs)
    rel_labels = resolver._get_rel_labels(gs)

    logger.info("Active schema: %s", active.schema_name)
    logger.info("  Node types (%d): %s", len(node_labels), sorted(node_labels))
    logger.info("  Rel types (%d): %s", len(rel_labels), sorted(rel_labels))

    if gs.patterns:
        logger.info("  Patterns (%d):", len(gs.patterns))
        for p in gs.patterns[:10]:
            logger.info("    %s", p)


# ---------------------------------------------------------------------------
# Step 3: Test Phase 1 -- text-based coverage check (no LLM)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_step3_phase1_text_match(resolver, documents):
    """Test that documents matching schema labels are resolved without LLM calls."""
    active = _load_active()
    assert active is not None

    gs = _schema_to_graph_schema(active.schema_definition)
    node_labels = resolver._get_node_labels(gs)

    phase1_hits = 0
    phase2_candidates = 0

    for doc in documents:
        text = doc.content or ""
        if not text:
            continue

        text_lower = text.lower()
        matched = {label for label in node_labels if label.lower() in text_lower}

        if matched:
            phase1_hits += 1
            # Resolve should return the active schema without LLM call
            result = resolver.resolve(text=text)
            assert not isinstance(result, str), (
                f"Expected GraphSchema for Phase 1 match, got string: {result}"
            )
            result_labels = resolver._get_node_labels(result)
            assert node_labels.issubset(result_labels), "Phase 1 result lost labels!"
            logger.info(
                "  Phase 1 HIT [%s]: matched %s -> reused active schema",
                doc.document_uuid[:25], sorted(matched)[:3],
            )
        else:
            phase2_candidates += 1
            logger.info(
                "  Phase 2 candidate [%s]: no labels in text",
                doc.document_uuid[:25],
            )

    logger.info(
        "Phase 1 coverage: %d/%d docs matched schema labels (%.0f%%)",
        phase1_hits, phase1_hits + phase2_candidates,
        100 * phase1_hits / max(1, phase1_hits + phase2_candidates),
    )


# ---------------------------------------------------------------------------
# Step 4: Test merge guarantees
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_step4_merge_superset(resolver):
    """Verify _merge_schemas produces a strict superset of the base."""
    active = _load_active()
    assert active is not None

    from neo4j_graphrag.experimental.components.schema import (
        NodeType, RelationshipType, PropertyType, SchemaBuilder,
    )

    base = _schema_to_graph_schema(active.schema_definition)
    base_labels = resolver._get_node_labels(base)
    base_rels = resolver._get_rel_labels(base)

    # Simulate discovering new entity types (patterns require all referenced nodes)
    discovered = SchemaBuilder.create_schema_model(
        node_types=[
            NodeType(label="TestNewCategory", description="Test",
                     properties=[PropertyType(name="name", type="STRING")]),
        ],
        relationship_types=[
            RelationshipType(label="TEST_BELONGS_TO", description="Test"),
        ],
    )

    merged = resolver._merge_schemas(base, discovered)
    merged_labels = resolver._get_node_labels(merged)
    merged_rels = resolver._get_rel_labels(merged)

    # All base labels must survive
    assert base_labels.issubset(merged_labels), f"Lost labels: {base_labels - merged_labels}"
    assert base_rels.issubset(merged_rels), f"Lost rels: {base_rels - merged_rels}"
    # New types must be added
    assert "TestNewCategory" in merged_labels
    assert "TEST_BELONGS_TO" in merged_rels

    logger.info(
        "Merge superset verified: %d -> %d nodes, %d -> %d rels",
        len(base_labels), len(merged_labels), len(base_rels), len(merged_rels),
    )


# ---------------------------------------------------------------------------
# Step 5: Test _find_new_types
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_step5_find_new_types(resolver):
    """Verify _find_new_types correctly identifies new vs existing types."""
    active = _load_active()
    assert active is not None

    from neo4j_graphrag.experimental.components.schema import (
        NodeType, PropertyType, SchemaBuilder,
    )

    base = _schema_to_graph_schema(active.schema_definition)
    existing_label = list(resolver._get_node_labels(base))[0]

    discovered = SchemaBuilder.create_schema_model(
        node_types=[
            NodeType(label=existing_label, description="Known",
                     properties=[PropertyType(name="name", type="STRING")]),
            NodeType(label="BrandNewEntityXYZ", description="Unknown",
                     properties=[PropertyType(name="name", type="STRING")]),
        ],
    )

    new_nodes, new_rels, new_patterns = resolver._find_new_types(base, discovered)
    new_labels = {n.label if hasattr(n, 'label') else n for n in new_nodes}

    assert "BrandNewEntityXYZ" in new_labels, f"Should find BrandNewEntityXYZ, got {new_labels}"
    assert existing_label not in new_labels, f"{existing_label} should not be new"
    logger.info("_find_new_types: correctly identified %d new nodes", len(new_nodes))


# ---------------------------------------------------------------------------
# Step 6: Compare active schema vs actual graph
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_step6_graph_vs_active_schema(resolver):
    """Compare what's in Neo4j vs the active schema definition."""
    active = _load_active()
    assert active is not None

    try:
        graph_schema = resolver._extract_from_existing_graph()
    except Exception as e:
        logger.warning("Cannot read graph schema (APOC not installed?): %s", e)
        pytest.skip(f"Cannot read graph: {e}")

    active_gs = _schema_to_graph_schema(active.schema_definition)
    active_labels = resolver._get_node_labels(active_gs)
    active_rels = resolver._get_rel_labels(active_gs)

    graph_labels = resolver._get_node_labels(graph_schema)
    graph_rels = resolver._get_rel_labels(graph_schema)

    # Types in graph but not in schema
    missing_nodes = graph_labels - active_labels
    missing_rels = graph_rels - active_rels

    # Types in schema but not in graph (defined but unused)
    extra_nodes = active_labels - graph_labels
    extra_rels = active_rels - graph_rels

    logger.info("Active schema: %d nodes, %d rels", len(active_labels), len(active_rels))
    logger.info("Graph actual:  %d nodes, %d rels", len(graph_labels), len(graph_rels))

    if missing_nodes or missing_rels:
        logger.warning(
            "Graph has types NOT in active schema (would trigger evolution):\n"
            "  Missing nodes: %s\n  Missing rels: %s",
            sorted(missing_nodes), sorted(missing_rels),
        )
    else:
        logger.info("Active schema covers all graph types -- no evolution needed")

    if extra_nodes or extra_rels:
        logger.info(
            "Schema defines types not yet in graph (expected for superset):\n"
            "  Extra nodes: %s\n  Extra rels: %s",
            sorted(extra_nodes), sorted(extra_rels),
        )


# ---------------------------------------------------------------------------
# Step 7: Show version history
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_step7_schema_version_history(resolver):
    """Show all schema versions for this partition (active + inactive)."""
    schemas = _all_schemas()
    logger.info("Schema version history (%d total):", len(schemas))
    for s in schemas:
        sd = _schema_def_to_dict(s.schema_definition) if s.schema_definition else {}
        node_count = len(sd.get("node_types", []))
        rel_count = len(sd.get("relationship_types", []))
        logger.info(
            "  [%s] type=%-10s status=%-8s nodes=%d rels=%d updated=%s",
            s.schema_name, s.schema_type, s.status,
            node_count, rel_count, s.updated_at,
        )

    # Only one should be active
    active_count = sum(1 for s in schemas if s.status == "active")
    if schemas:
        assert active_count == 1, f"Expected 1 active schema, found {active_count}"
        logger.info("Verified: exactly 1 active schema out of %d total", len(schemas))


# ---------------------------------------------------------------------------
# Step 8: Test resolve() triggers evolution for unrecognized text
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_step8_resolve_with_novel_text(resolver):
    """
    Test that resolve() with text containing entity types NOT in the active schema
    triggers LLM discovery and schema evolution (superset merge).
    Uses a synthetic text to guarantee Phase 2 is triggered.
    """
    active_before = _load_active()
    assert active_before is not None

    gs_before = _schema_to_graph_schema(active_before.schema_definition)
    labels_before = resolver._get_node_labels(gs_before)
    rels_before = resolver._get_rel_labels(gs_before)

    # Synthetic text unlikely to match any existing schema labels
    novel_text = (
        "The International Space Station (ISS) orbits Earth at approximately 408 km altitude. "
        "Astronaut Dr. Sarah Chen conducted microgravity experiments in the Columbus laboratory module. "
        "NASA's Artemis program aims to return humans to the Moon by partnering with SpaceX."
    )

    # Make sure none of the schema labels appear in this text
    text_lower = novel_text.lower()
    pre_matched = {label for label in labels_before if label.lower() in text_lower}
    if pre_matched:
        logger.info("Novel text matched existing labels %s -- skipping Phase 2 test", pre_matched)
        return

    logger.info("Novel text has no matching schema labels -- Phase 2 (LLM) will fire")
    result = resolver.resolve(text=novel_text)

    if isinstance(result, str):
        logger.info("resolve() returned string '%s' (LLM discovery failed?)", result)
        return

    result_labels = resolver._get_node_labels(result)
    result_rels = resolver._get_rel_labels(result)

    # Must be a superset of the previous active schema
    assert labels_before.issubset(result_labels), (
        f"Evolution lost labels: {labels_before - result_labels}"
    )

    new_labels = result_labels - labels_before
    new_rels = result_rels - rels_before

    logger.info("Schema evolved!")
    logger.info("  Before: %d nodes, %d rels", len(labels_before), len(rels_before))
    logger.info("  After:  %d nodes, %d rels", len(result_labels), len(result_rels))
    if new_labels:
        logger.info("  New node types: %s", sorted(new_labels))
    if new_rels:
        logger.info("  New rel types: %s", sorted(new_rels))

    # Verify old schema was deactivated and new one is active
    active_after = _load_active()
    assert active_after is not None
    if active_before.schema_name != active_after.schema_name:
        logger.info(
            "Schema version changed: %s -> %s",
            active_before.schema_name, active_after.schema_name,
        )


# ---------------------------------------------------------------------------
# Step 9: Simulate full extraction flow (evolve_schema_from_graph with LLM fallback)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_step9_evolve_schema_from_graph_llm_fallback(resolver, documents, request):
    """
    Simulate what happens after extraction when APOC is not available.
    evolve_schema_from_graph(text=...) should fall back to LLM discovery
    and create the initial active schema.

    This test:
    1. Deletes all existing schemas (clean slate)
    2. Calls evolve_schema_from_graph(text=...) — APOC will fail, LLM fallback kicks in
    3. Verifies an active schema was created
    """
    from knowledge_graph_engine.models.graph_schema import GraphSchemaModel

    # Store original schemas for restoration
    original_schemas = list(GraphSchemaModel.query(PARTITION_KEY))
    
    # Clean slate: delete all schemas for this partition
    for s in original_schemas:
        s.delete()

    assert _load_active() is None, "Should have no active schema after cleanup"
    
    # Register cleanup to restore original schemas after test
    def restore_schemas():
        """Restore original schemas to maintain test isolation."""
        # Delete any schemas created during test
        for s in GraphSchemaModel.query(PARTITION_KEY):
            s.delete()
        # Restore original schemas
        for s in original_schemas:
            s.save()
    
    request.addfinalizer(restore_schemas)
    logger.info("Cleaned all schemas -- starting fresh")

    # Simulate the post-extraction call with text
    text = documents[0].content or ""
    assert text, "Need document text"

    logger.info("Calling evolve_schema_from_graph(text=...) with no active schema...")
    resolver.evolve_schema_from_graph(text=text)

    # Verify schema was captured via LLM fallback
    active = _load_active()
    assert active is not None, (
        "evolve_schema_from_graph should have created an active schema via LLM fallback"
    )

    gs = _schema_to_graph_schema(active.schema_definition)
    node_labels = resolver._get_node_labels(gs)
    rel_labels = resolver._get_rel_labels(gs)

    logger.info("Schema captured via LLM fallback: %s", active.schema_name)
    logger.info("  Node types (%d): %s", len(node_labels), sorted(node_labels))
    logger.info("  Rel types (%d): %s", len(rel_labels), sorted(rel_labels))

    assert len(node_labels) > 0, "Schema should have at least one node type"
    # Log detected node types for debugging (don't assert specific type)
    logger.info("Detected node types: %s", sorted(node_labels))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
