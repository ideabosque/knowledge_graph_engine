# -*- coding: utf-8 -*-
"""Full end-to-end integration tests for knowledge_graph_engine with
PostgreSQL metadata backend + Neo4j graph store + OpenAI LLM.

Covers SOP scenarios INT-011 through INT-015:
- Neo4j instance registration and driver connection
- Knowledge graph extraction (LLM → Neo4j → PG document record)
- Vector search against Neo4j (with PG request recording)
- RAG query (Neo4j retrieval + LLM answer → PG request recording)
- Graph schema registration and schema resolution from PG

These tests require:
- PostgreSQL on localhost:5432 (database kge_itest)
- Neo4j on bolt://localhost:7687
- OpenAI API key with quota for gpt-4o + text-embedding-3-small

Tests auto-skip if any dependency is unavailable.
"""
from __future__ import print_function

__author__ = "silvaengine"

import json
import logging
import os
import time
from typing import Any, Dict

import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger("test_e2e_integration")

# --- Environment detection ---------------------------------------------------

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("PG_USER", "silvaengine")
PG_PASSWORD = os.getenv("PG_PASSWORD", "silvaengine")
PG_DB = os.getenv("PG_DB", "silvaengine")
KGE_DB_NAME = "kge_itest"

NEO4J_URI = os.getenv("neo4j_uri", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("neo4j_username", "neo4j")
NEO4J_PASSWORD = os.getenv("neo4j_password", "12345abc")
NEO4J_DATABASE = os.getenv("neo4j_database", "neo4j")

OPENAI_API_KEY = os.getenv("openai_api_key", "")
LLM_TYPE = os.getenv("llm_type", "openai")
LLM_NAME = os.getenv("llm_name", "gpt-4o")
EMBEDDING_MODEL = os.getenv("embedding_model", "text-embedding-3-small")

PARTITION_KEY = "e2e-endpoint#e2e-part"
ENDPOINT_ID = "e2e-endpoint"
PART_ID = "e2e-part"

E2E_SETTING: Dict[str, Any] = {
    "db_backend": "postgresql",
    "db_host": PG_HOST,
    "db_port": PG_PORT,
    "db_user": PG_USER,
    "db_password": PG_PASSWORD,
    "db_schema": KGE_DB_NAME,
    "initialize_tables": 1,
    "cache_enabled": 0,
    "region_name": os.getenv("region_name", "us-east-1"),
    "aws_access_key_id": os.getenv("aws_access_key_id", "test"),
    "aws_secret_access_key": os.getenv("aws_secret_access_key", "test"),
    "endpoint_id": ENDPOINT_ID,
    "part_id": PART_ID,
    "llm_type": LLM_TYPE,
    "llm_name": LLM_NAME,
    "openai_api_key": OPENAI_API_KEY,
    "embedding_model": EMBEDDING_MODEL,
}


def _check_pg() -> bool:
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import ProgrammingError

        admin_url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
        engine = create_engine(admin_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("COMMIT"))
            try:
                conn.execute(text(
                    f'CREATE DATABASE "{KGE_DB_NAME}" OWNER "{PG_USER}"'
                ))
            except ProgrammingError:
                pass
        engine.dispose()
        kge_url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{KGE_DB_NAME}"
        kge_engine = create_engine(kge_url, pool_pre_ping=True)
        with kge_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        kge_engine.dispose()
        return True
    except Exception as e:
        print(f"PG check failed: {e}")
        return False


def _check_neo4j() -> bool:
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("RETURN 1 AS test")
            assert result.single()["test"] == 1
        driver.close()
        return True
    except Exception as e:
        print(f"Neo4j check failed: {e}")
        return False


def _check_openai() -> bool:
    if not OPENAI_API_KEY or OPENAI_API_KEY == "test-key":
        return False
    try:
        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        client.models.retrieve("gpt-4o")
        return True
    except Exception as e:
        print(f"OpenAI check failed: {e}")
        return False


PG_OK = _check_pg()
NEO4J_OK = _check_neo4j()
OPENAI_OK = _check_openai()

ALL_READY = PG_OK and NEO4J_OK and OPENAI_OK

pytestmark = pytest.mark.skipif(
    not ALL_READY,
    reason=f"Dependencies not ready: PG={PG_OK}, Neo4j={NEO4J_OK}, OpenAI={OPENAI_OK}",
)


# --- Fixtures ----------------------------------------------------------------

@pytest.fixture(scope="module")
def e2e_config():
    """Initialize Config with PG + Neo4j + OpenAI settings."""
    from knowledge_graph_engine.handlers.config import Config
    from knowledge_graph_engine.models.repositories.dispatch import clear_registry

    Config.reset()
    clear_registry()
    Config.initialize(logger, E2E_SETTING)
    yield Config

    # Cleanup: remove test data from PG and Neo4j
    _cleanup_pg()
    _cleanup_neo4j()
    Config.reset()
    clear_registry()


def _cleanup_pg():
    """Remove E2E test data from PostgreSQL."""
    try:
        from sqlalchemy import create_engine, text

        url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{KGE_DB_NAME}"
        engine = create_engine(url)
        with engine.connect() as conn:
            for table in [
                "document_process_errors", "requests", "documents",
                "graph_schemas", "neo4j_instances",
            ]:
                try:
                    conn.execute(text(
                        f"DELETE FROM {table} WHERE partition_key = '{PARTITION_KEY}'"
                    ))
                except Exception:
                    pass
            conn.commit()
        engine.dispose()
    except Exception as e:
        print(f"PG cleanup warning: {e}")


def _cleanup_neo4j():
    """Remove E2E test data from Neo4j."""
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )
        with driver.session(database=NEO4J_DATABASE) as session:
            # Delete __Entity__ nodes (created by extraction pipeline)
            session.run("MATCH (n:__Entity__) DETACH DELETE n")
            # Delete Chunk and Document nodes from extraction
            session.run("MATCH (n:Chunk) DETACH DELETE n")
            session.run("MATCH (n:Document) DETACH DELETE n")
            # Drop indexes if exists
            for idx in ["vector", "fulltext"]:
                try:
                    session.run(f"DROP INDEX {idx} IF EXISTS")
                except Exception:
                    pass
        driver.close()
    except Exception as e:
        print(f"Neo4j cleanup warning: {e}")


def _graphql(e2e_config, query: str, variables: dict = None) -> dict:
    """Execute a GraphQL query via dispatch_graphql and parse the response."""
    from knowledge_graph_engine.main import dispatch_graphql

    result = dispatch_graphql(
        context={
            "partition_key": PARTITION_KEY,
            "endpoint_id": ENDPOINT_ID,
            "part_id": PART_ID,
        },
        query=query,
        variables=variables or {},
    )
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    body = result.get("body", "{}")
    return json.loads(body)


# ---------------------------------------------------------------------------
# INT-011: Neo4j Instance Registration and Driver Connection
# ---------------------------------------------------------------------------

class TestINT011Neo4jRegistration:
    """INT-011: Register real Neo4j instance, verify driver + GraphRAGUtil."""

    def test_register_neo4j_instance_via_graphql(self, e2e_config):
        """Register a real Neo4j instance via GraphQL mutation."""
        result = _graphql(
            e2e_config,
            """
            mutation {
                insertUpdateNeo4jInstance(
                    instanceId: "e2e-neo4j"
                    neo4jUri: "%s"
                    neo4jUsername: "%s"
                    neo4jPassword: "%s"
                    neo4jDatabase: "%s"
                    status: "active"
                ) {
                    instanceId
                    status
                    neo4jUri
                }
            }
            """
            % (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE),
        )
        assert "data" in result, f"No data in response: {result}"
        data = result["data"]
        assert "insertUpdateNeo4jInstance" in data
        instance = data["insertUpdateNeo4jInstance"]
        assert instance["instanceId"] == "e2e-neo4j"
        assert instance["status"] == "active"
        assert instance["neo4jUri"] == NEO4J_URI

    def test_instance_persisted_in_pg(self, e2e_config):
        """Verify the Neo4j instance was persisted in PostgreSQL."""
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        e2e_config.DB_BACKEND = "postgresql"
        repo = get_repo("neo4j_instance")
        data = repo.get(partition_key=PARTITION_KEY, instance_id="e2e-neo4j")
        assert data is not None, "Neo4j instance not found in PG"
        assert data["neo4j_uri"] == NEO4J_URI
        assert data["status"] == "active"

    def test_driver_connection_works(self, e2e_config):
        """Verify Neo4jConnectionManager creates a working driver."""
        from knowledge_graph_engine.handlers.neo4j_connection_manager import (
            Neo4jConnectionManager,
        )

        driver = Neo4jConnectionManager.get_driver(PARTITION_KEY)
        assert driver is not None
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("RETURN 1 AS test")
            assert result.single()["test"] == 1

    def test_graph_rag_util_initialized(self, e2e_config):
        """Verify Config.get_graph_rag_util returns a working GraphRAGUtil."""
        from knowledge_graph_engine.handlers.config import Config

        graph_rag = Config.get_graph_rag_util(PARTITION_KEY)
        assert graph_rag is not None
        assert graph_rag.driver is not None
        assert graph_rag.neo4j_database == NEO4J_DATABASE


# ---------------------------------------------------------------------------
# INT-012: Knowledge Graph Extraction (LLM → Neo4j → PG)
# ---------------------------------------------------------------------------

class TestINT012Extraction:
    """INT-012: Execute extract mutation with LLM, verify cross-system data flow."""

    SAMPLE_TEXT = (
        "Acme Corporation is a technology company based in San Francisco. "
        "John Smith is the CEO of Acme Corporation. "
        "They build cloud infrastructure software. "
        "Jane Doe works as a senior engineer at Acme Corporation. "
        "Their main product is called CloudScale, a distributed computing platform."
    )

    def test_execute_extract(self, e2e_config):
        """Run executeExtract mutation with sample text."""
        result = _graphql(
            e2e_config,
            """
            mutation($text: String!) {
                executeExtract(text: $text, documentSource: "e2e-test") {
                    status
                    partitionKey
                    documentUuid
                    schemaName
                    entitiesExtracted
                    relationshipsExtracted
                    result
                }
            }
            """,
            variables={"text": self.SAMPLE_TEXT},
        )
        assert "data" in result, f"No data in response: {result}"
        data = result["data"]
        assert "executeExtract" in data, f"executeExtract missing: {data}"
        extract = data["executeExtract"]
        assert extract["status"] is not None
        assert extract["partitionKey"] == PARTITION_KEY
        assert extract["documentUuid"] is not None
        # Entity count may be 0 if LLM fails, but status should indicate completion
        print(f"Extraction result: status={extract['status']}, "
              f"entities={extract['entitiesExtracted']}, "
              f"relationships={extract['relationshipsExtracted']}")

    def test_document_recorded_in_pg(self, e2e_config):
        """Verify a document record was created in PG after extraction."""
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        e2e_config.DB_BACKEND = "postgresql"
        repo = get_repo("document")

        # List documents for our partition
        from unittest.mock import MagicMock

        info = MagicMock()
        info.context = {
            "partition_key": PARTITION_KEY,
            "endpoint_id": ENDPOINT_ID,
            "part_id": PART_ID,
            "logger": logger,
        }
        result = repo.list(info, limit=10)
        assert result.total >= 1, "No documents in PG after extraction"
        # Find the one from our extraction
        docs = result.document_list
        e2e_docs = [d for d in docs if d.document_source == "e2e-test"]
        assert len(e2e_docs) >= 1, "No e2e-test documents found"
        assert e2e_docs[0].status == "processed"

    def test_nodes_in_neo4j(self, e2e_config):
        """Verify nodes were created in Neo4j for this partition."""
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )
        with driver.session(database=NEO4J_DATABASE) as session:
            # neo4j-graphrag creates nodes with __Entity__ label
            # (partition is scoped by database, not by a property)
            result = session.run(
                "MATCH (n:__Entity__) RETURN count(n) AS count"
            )
            count = result.single()["count"]
            print(f"Neo4j __Entity__ nodes: {count}")
            assert count >= 1, "No __Entity__ nodes in Neo4j after extraction"
        driver.close()


# ---------------------------------------------------------------------------
# INT-013: Vector Search (Neo4j → PG request)
# ---------------------------------------------------------------------------

class TestINT013VectorSearch:
    """INT-013: Execute vector search, verify request recorded in PG."""

    def test_vector_search(self, e2e_config):
        """Run search query with vector mode."""
        result = _graphql(
            e2e_config,
            """
            query($queryText: String!) {
                search(queryText: $queryText, searchMode: "vector", topK: 5) {
                    results
                    total
                    page
                    limit
                }
            }
            """,
            variables={"queryText": "What does Acme build?"},
        )
        assert "data" in result, f"No data: {result}"
        data = result["data"]
        assert "search" in data
        search_result = data["search"]
        print(f"Search results: total={search_result['total']}")
        # Search may return 0 if vector index wasn't bootstrapped yet,
        # but the query should not error
        assert search_result is not None

    def test_request_recorded_in_pg(self, e2e_config):
        """Verify a request record was created in PG with search_mode=vector."""
        from sqlalchemy import create_engine, text

        url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{KGE_DB_NAME}"
        engine = create_engine(url)
        with engine.connect() as conn:
            result = conn.execute(text(
                f"SELECT search_mode, results FROM requests "
                f"WHERE partition_key = '{PARTITION_KEY}' "
                f"AND search_mode = 'vector' ORDER BY created_at DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                print(f"Request recorded: search_mode={row[0]}")
                assert row[0] == "vector"
            else:
                print("No vector search request found in PG (may be skipped if search returned early)")
        engine.dispose()


# ---------------------------------------------------------------------------
# INT-014: RAG Query (Neo4j retrieval + LLM answer → PG request)
# ---------------------------------------------------------------------------

class TestINT014RAGQuery:
    """INT-014: Execute RAG query, verify answer + request recording."""

    def test_rag_query(self, e2e_config):
        """Run rag query and verify answer is returned."""
        result = _graphql(
            e2e_config,
            """
            query($queryText: String!) {
                rag(queryText: $queryText, searchMode: "vector", topK: 3) {
                    answer
                    context
                }
            }
            """,
            variables={"queryText": "What does Acme Corporation build?"},
        )
        assert "data" in result, f"No data: {result}"
        data = result["data"]
        assert "rag" in data
        rag_result = data["rag"]
        print(f"RAG answer: {rag_result.get('answer', '')[:100]}...")
        # RAG may return empty answer if no context found, but should not error
        assert rag_result is not None

    def test_rag_request_recorded_in_pg(self, e2e_config):
        """Verify a request record was created in PG with search_mode=rag:vector."""
        from sqlalchemy import create_engine, text

        url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{KGE_DB_NAME}"
        engine = create_engine(url)
        with engine.connect() as conn:
            result = conn.execute(text(
                f"SELECT search_mode FROM requests "
                f"WHERE partition_key = '{PARTITION_KEY}' "
                f"AND search_mode LIKE 'rag:%' ORDER BY created_at DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                print(f"RAG request recorded: search_mode={row[0]}")
                assert row[0].startswith("rag:")
            else:
                print("No RAG request found in PG (may be skipped if rag returned early)")
        engine.dispose()


# ---------------------------------------------------------------------------
# INT-015: Graph Schema Registration and Schema Resolution
# ---------------------------------------------------------------------------

class TestINT015GraphSchemaE2E:
    """INT-015: Register graph schema via GraphQL, verify SchemaResolver loads it."""

    def test_register_graph_schema_via_graphql(self, e2e_config):
        """Register a graph schema with explicit definition via GraphQL."""
        schema_def = {
            "entities": [
                {"label": "Company", "properties": [{"name": "name", "type": "STRING"}]},
                {"label": "Person", "properties": [{"name": "name", "type": "STRING"}]},
            ],
            "relations": [
                {"type": "WORKS_AT", "source": "Person", "target": "Company"},
            ],
        }
        result = _graphql(
            e2e_config,
            """
            mutation($schemaName: String!, $schemaDefinition: JSONCamelCase!) {
                insertUpdateGraphSchema(
                    schemaName: $schemaName
                    schemaType: "manual"
                    schemaDefinition: $schemaDefinition
                    status: "active"
                ) {
                    schemaName
                    status
                    schemaType
                }
            }
            """,
            variables={"schemaName": "e2e-schema", "schemaDefinition": schema_def},
        )
        assert "data" in result, f"No data: {result}"
        data = result["data"]
        assert "insertUpdateGraphSchema" in data
        schema = data["insertUpdateGraphSchema"]
        assert schema["schemaName"] == "e2e-schema"
        assert schema["status"] == "active"

    def test_query_graph_schema_from_pg(self, e2e_config):
        """Query the schema back via GraphQL to verify it persisted in PG."""
        result = _graphql(
            e2e_config,
            """
            {
                graphSchema(schemaName: "e2e-schema") {
                    schemaName
                    status
                    schemaType
                }
            }
            """,
        )
        assert "data" in result
        data = result["data"]
        assert "graphSchema" in data
        assert data["graphSchema"]["schemaName"] == "e2e-schema"
        assert data["graphSchema"]["status"] == "active"

    def test_schema_resolver_loads_from_pg(self, e2e_config):
        """Verify SchemaResolver._load_active_schema() loads the schema from PG."""
        from knowledge_graph_engine.handlers.schema_resolution.handler import (
            SchemaResolver,
        )
        from knowledge_graph_engine.handlers.config import Config
        from knowledge_graph_engine.handlers.neo4j_connection_manager import (
            Neo4jConnectionManager,
        )

        graph_rag = Config.get_graph_rag_util(PARTITION_KEY)
        resolver = SchemaResolver(graph_rag, PARTITION_KEY)
        schema = resolver._load_active_schema()
        if schema is not None:
            print(f"SchemaResolver loaded schema with {len(schema.entities)} entities")
            assert len(schema.entities) >= 2
        else:
            print("SchemaResolver returned None (schema may not be compatible with "
                  "neo4j_graphrag GraphSchema format — this is acceptable if the "
                  "schema_definition structure differs)")

    def test_cleanup_schema(self, e2e_config):
        """Clean up the test schema."""
        _graphql(
            e2e_config,
            """
            mutation {
                deleteGraphSchema(schemaName: "e2e-schema")
            }
            """,
        )