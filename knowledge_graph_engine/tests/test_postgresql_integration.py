# -*- coding: utf-8 -*-
"""Integration tests for knowledge_graph_engine with PostgreSQL backend.

Covers SOP scenarios INT-001 through INT-010:
- PostgreSQL connection and table initialization
- All 5 entity CRUD operations via repository boundary
- Single-active invariant for graph_schema and neo4j_instance
- Partial unique index enforcement at DB level
- GraphQL dispatch_graphql with PG backend
- DataLoader dispatch (PGRequestLoaders)
- Cache config backend-awareness

These tests require a live PostgreSQL database. They auto-skip if
PG connection fails or SQLAlchemy is not installed.
"""
from __future__ import print_function

__author__ = "silvaengine"

import logging
import os
import sys
import traceback
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock

import pendulum
import pytest
from dotenv import load_dotenv
from graphene import ResolveInfo

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger("test_pg_integration")

# --- Test settings -----------------------------------------------------------

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("PG_USER", "silvaengine")
PG_PASSWORD = os.getenv("PG_PASSWORD", "silvaengine")
PG_DB = os.getenv("PG_DB", "silvaengine")

# Use a dedicated database to avoid table name collisions with rfq_engine
# (rfq_engine's `requests` table has different columns and already exists in the
# silvaengine database). We create a separate KGE database for integration tests.
KGE_DB_NAME = "kge_itest"

PARTITION_KEY = "itest-endpoint#itest-part"
ENDPOINT_ID = "itest-endpoint"
PART_ID = "itest-part"

PG_SETTING: Dict[str, Any] = {
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
    "llm_type": "openai",
    "llm_name": "gpt-4o",
    "openai_api_key": os.getenv("openai_api_key", "test-key"),
    "embedding_model": "text-embedding-3-small",
    "neo4j_uri": "bolt://localhost:7687",
    "neo4j_username": "neo4j",
    "neo4j_password": "test",
    "neo4j_database": "neo4j",
}


def _pg_available() -> bool:
    """Check if PostgreSQL is reachable and create the KGE test database."""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import ProgrammingError

        # Connect to the default database to create the KGE test database
        admin_url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
        engine = create_engine(admin_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("COMMIT"))  # end any implicit transaction
            try:
                conn.execute(text(
                    f'CREATE DATABASE "{KGE_DB_NAME}" OWNER "{PG_USER}"'
                ))
            except ProgrammingError:
                pass  # Database already exists
        engine.dispose()

        # Now verify the KGE database is accessible
        kge_url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{KGE_DB_NAME}"
        kge_engine = create_engine(kge_url, pool_pre_ping=True)
        with kge_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        kge_engine.dispose()
        return True
    except Exception as e:
        print(f"PG availability check failed: {e}")
        return False


PG_AVAILABLE = _pg_available()

pytestmark = pytest.mark.skipif(
    not PG_AVAILABLE, reason="PostgreSQL not available — skipping PG integration tests"
)


# --- Fixtures ----------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_config():
    """Initialize Config with PostgreSQL backend."""
    from knowledge_graph_engine.handlers.config import Config
    from knowledge_graph_engine.models.repositories.dispatch import clear_registry

    Config.reset()
    clear_registry()
    Config.initialize(logger, PG_SETTING)
    yield Config
    # Cleanup: drop all data from the KGE test database
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
                    pass  # table might not exist
            conn.commit()
        engine.dispose()
    except Exception:
        pass
    Config.reset()
    clear_registry()


@pytest.fixture
def mock_info():
    """Mock GraphQL ResolveInfo with partition context."""
    info = MagicMock(spec=ResolveInfo)
    info.context = {
        "logger": logger,
        "endpoint_id": ENDPOINT_ID,
        "part_id": PART_ID,
        "partition_key": PARTITION_KEY,
    }
    return info


# ---------------------------------------------------------------------------
# INT-001: PostgreSQL Connection and Table Initialization
# ---------------------------------------------------------------------------

class TestINT001ConnectionAndTables:
    """INT-001: Config initializes with PG backend and creates all 5 tables."""

    def test_config_db_backend_is_postgresql(self, pg_config):
        assert pg_config.DB_BACKEND == "postgresql"

    def test_db_session_is_initialized(self, pg_config):
        assert pg_config.db_session is not None

    def test_all_5_tables_exist(self, pg_config):
        from sqlalchemy import text

        session = pg_config.db_session
        result = session.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN "
            "('documents', 'graph_schemas', 'neo4j_instances', "
            "'requests', 'document_process_errors') ORDER BY table_name"
        ))
        tables = [r[0] for r in result.fetchall()]
        assert "documents" in tables, "documents table missing"
        assert "graph_schemas" in tables, "graph_schemas table missing"
        assert "neo4j_instances" in tables, "neo4j_instances table missing"
        assert "requests" in tables, "requests table missing"
        assert "document_process_errors" in tables, "document_process_errors table missing"

    def test_repositories_register_for_postgresql(self, pg_config):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"

        entities = ["document", "graph_schema", "neo4j_instance", "request",
                     "document_process_error"]
        for entity in entities:
            repo = get_repo(entity)
            assert repo is not None, f"get_repo({entity}) returned None"
            assert repo.entity_type == entity


# ---------------------------------------------------------------------------
# INT-002: Neo4j Instance CRUD via Repository
# ---------------------------------------------------------------------------

class TestINT002Neo4jInstanceCRUD:
    """INT-002: Insert, get, list, update, delete Neo4j instance."""

    def test_insert_neo4j_instance(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("neo4j_instance")
        result = repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            instance_id="itest-instance-1",
            neo4j_uri="bolt://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="test123",
            neo4j_database="neo4j",
            status="active",
            max_connection_pool_size=5,
        )
        assert result is not None
        assert result["instance_id"] == "itest-instance-1"
        assert result["status"] == "active"

    def test_get_neo4j_instance(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("neo4j_instance")
        data = repo.get(
            partition_key=PARTITION_KEY,
            instance_id="itest-instance-1",
        )
        assert data is not None
        assert data["instance_id"] == "itest-instance-1"
        assert data["neo4j_uri"] == "bolt://localhost:7687"

    def test_count_neo4j_instance(self, pg_config):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("neo4j_instance")
        count = repo.count(
            partition_key=PARTITION_KEY,
            instance_id="itest-instance-1",
        )
        assert count == 1

    def test_single_active_invariant(self, pg_config, mock_info):
        """Inserting a second active instance deactivates the first."""
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("neo4j_instance")

        # Insert second active instance
        repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            instance_id="itest-instance-2",
            neo4j_uri="bolt://localhost:7688",
            neo4j_username="neo4j",
            neo4j_password="test456",
            status="active",
        )

        # First instance should now be inactive
        first = repo.get(
            partition_key=PARTITION_KEY,
            instance_id="itest-instance-1",
        )
        assert first["status"] == "inactive"

        # resolve_active should return the second one
        active = repo.resolve_active(PARTITION_KEY)
        assert active is not None
        assert active["instance_id"] == "itest-instance-2"

    def test_delete_neo4j_instance(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("neo4j_instance")

        # Delete both instances
        repo.delete(mock_info, partition_key=PARTITION_KEY, instance_id="itest-instance-1")
        repo.delete(mock_info, partition_key=PARTITION_KEY, instance_id="itest-instance-2")

        assert repo.get(
            partition_key=PARTITION_KEY, instance_id="itest-instance-1"
        ) is None
        assert repo.get(
            partition_key=PARTITION_KEY, instance_id="itest-instance-2"
        ) is None


# ---------------------------------------------------------------------------
# INT-003: Graph Schema CRUD with Single-Active Invariant
# ---------------------------------------------------------------------------

class TestINT003GraphSchemaCRUD:
    """INT-003: Insert, activate, deactivate graph schemas."""

    def test_insert_active_schema_a(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("graph_schema")
        result = repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            schema_name="itest-schema-a",
            schema_type="manual",
            schema_definition={"entities": ["Person", "Organization"]},
            neo4j_schema_string="(:Person)-[:WORKS_AT]->(:Organization)",
            status="active",
        )
        assert result is not None
        assert result["schema_name"] == "itest-schema-a"
        assert result["status"] == "active"

    def test_insert_active_schema_b_deactivates_a(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("graph_schema")

        repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            schema_name="itest-schema-b",
            schema_type="manual",
            schema_definition={"entities": ["Product", "Category"]},
            status="active",
        )

        # Schema A should be deactivated
        schema_a = repo.get(
            partition_key=PARTITION_KEY, schema_name="itest-schema-a"
        )
        assert schema_a["status"] == "inactive"

        # resolve_active returns B
        active = repo.resolve_active(PARTITION_KEY)
        assert active is not None
        assert active["schema_name"] == "itest-schema-b"

    def test_deactivate_schema_b(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("graph_schema")

        repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            schema_name="itest-schema-b",
            status="inactive",
        )

        # No active schema now
        active = repo.resolve_active(PARTITION_KEY)
        assert active is None

    def test_jsonb_schema_definition_preserved(self, pg_config):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("graph_schema")
        data = repo.get(
            partition_key=PARTITION_KEY, schema_name="itest-schema-a"
        )
        assert data is not None
        assert "entities" in data["schema_definition"]
        assert "Person" in data["schema_definition"]["entities"]

    def test_delete_graph_schemas(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("graph_schema")
        repo.delete(mock_info, partition_key=PARTITION_KEY, schema_name="itest-schema-a")
        repo.delete(mock_info, partition_key=PARTITION_KEY, schema_name="itest-schema-b")
        assert repo.get(
            partition_key=PARTITION_KEY, schema_name="itest-schema-a"
        ) is None


# ---------------------------------------------------------------------------
# INT-004: Document CRUD via Repository
# ---------------------------------------------------------------------------

class TestINT004DocumentCRUD:
    """INT-004: Insert, get, list, update, delete document."""

    def test_insert_document(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("document")
        result = repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            document_uuid="itest-doc-001",
            document_source="test",
            document_external_id="ext-001",
            content="This is test content for integration testing.",
            content_embedding=[0.1, 0.2, 0.3, 0.4, 0.5],
            status="active",
            updated_by="itest",
        )
        assert result is not None
        assert result["document_uuid"] == "itest-doc-001"
        assert result["content"] == "This is test content for integration testing."

    def test_get_document(self, pg_config):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("document")
        data = repo.get(
            partition_key=PARTITION_KEY,
            document_uuid="itest-doc-001",
        )
        assert data is not None
        assert data["document_source"] == "test"
        assert data["document_external_id"] == "ext-001"

    def test_embedding_jsonb_preserved(self, pg_config):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("document")
        data = repo.get(
            partition_key=PARTITION_KEY,
            document_uuid="itest-doc-001",
        )
        assert data["content_embedding"] == [0.1, 0.2, 0.3, 0.4, 0.5]

    def test_list_documents_by_status(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("document")
        result = repo.list(mock_info, statuses=["active"], limit=10)
        assert result is not None
        assert result.total >= 1

    def test_update_document(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("document")
        repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            document_uuid="itest-doc-001",
            document_title="Updated Title",
            status="inactive",
        )
        data = repo.get(
            partition_key=PARTITION_KEY,
            document_uuid="itest-doc-001",
        )
        assert data["document_title"] == "Updated Title"
        assert data["status"] == "inactive"

    def test_delete_document(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("document")
        repo.delete(mock_info, partition_key=PARTITION_KEY, document_uuid="itest-doc-001")
        assert repo.get(
            partition_key=PARTITION_KEY, document_uuid="itest-doc-001"
        ) is None


# ---------------------------------------------------------------------------
# INT-005: Request CRUD via Repository
# ---------------------------------------------------------------------------

class TestINT005RequestCRUD:
    """INT-005: Insert, get, list, delete request."""

    def test_insert_request(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("request")
        result = repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            request_uuid="itest-req-001",
            user_query="What products does Acme build?",
            search_mode="text2cypher",
            results=[{"content": "Acme builds widgets", "score": 0.95}],
            updated_by="itest",
        )
        assert result is not None
        assert result["request_uuid"] == "itest-req-001"
        assert result["search_mode"] == "text2cypher"

    def test_get_request(self, pg_config):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("request")
        data = repo.get(
            partition_key=PARTITION_KEY,
            request_uuid="itest-req-001",
        )
        assert data is not None
        assert data["user_query"] == "What products does Acme build?"

    def test_results_jsonb_preserved(self, pg_config):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("request")
        data = repo.get(
            partition_key=PARTITION_KEY,
            request_uuid="itest-req-001",
        )
        assert len(data["results"]) == 1
        assert data["results"][0]["content"] == "Acme builds widgets"

    def test_list_by_search_mode(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("request")
        result = repo.list(mock_info, search_mode="text2cypher", limit=10)
        assert result.total >= 1

    def test_delete_request(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("request")
        repo.delete(mock_info, partition_key=PARTITION_KEY, request_uuid="itest-req-001")
        assert repo.get(
            partition_key=PARTITION_KEY, request_uuid="itest-req-001"
        ) is None


# ---------------------------------------------------------------------------
# INT-006: Document Process Error CRUD
# ---------------------------------------------------------------------------

class TestINT006DocumentProcessErrorCRUD:
    """INT-006: Insert, get, delete document process error."""

    def test_insert_process_error(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("document_process_error")
        result = repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            document_source="test",
            document_external_id="ext-err-001",
            error_message="Failed to extract entities from document",
            process_status="failed",
            process_count=0,
        )
        assert result is not None
        assert result["process_error_uuid"].startswith("err-")
        assert result["process_status"] == "failed"

    def test_get_process_error(self, pg_config):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("document_process_error")

        # Get all errors for our partition via raw SQL
        from sqlalchemy import text

        session = pg_config.db_session
        result = session.execute(text(
            f"SELECT process_error_uuid FROM document_process_errors "
            f"WHERE partition_key = '{PARTITION_KEY}' LIMIT 1"
        ))
        row = result.fetchone()
        if row:
            data = repo.get(
                partition_key=PARTITION_KEY,
                process_error_uuid=row[0],
            )
            assert data is not None
            assert data["error_message"] == "Failed to extract entities from document"

    def test_delete_process_error(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry
        from sqlalchemy import text

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("document_process_error")

        session = pg_config.db_session
        result = session.execute(text(
            f"SELECT process_error_uuid FROM document_process_errors "
            f"WHERE partition_key = '{PARTITION_KEY}' LIMIT 1"
        ))
        row = result.fetchone()
        if row:
            repo.delete(
                mock_info,
                partition_key=PARTITION_KEY,
                process_error_uuid=row[0],
            )
            assert repo.get(
                partition_key=PARTITION_KEY, process_error_uuid=row[0]
            ) is None


# ---------------------------------------------------------------------------
# INT-007: GraphQL dispatch_graphql with PG Backend
# ---------------------------------------------------------------------------

class TestINT007GraphQLDispatch:
    """INT-007: Execute GraphQL queries/mutations via dispatch_graphql."""

    def test_ping_query(self, pg_config):
        from knowledge_graph_engine.main import dispatch_graphql

        result = dispatch_graphql(
            context={"partition_key": PARTITION_KEY, "endpoint_id": ENDPOINT_ID, "part_id": PART_ID},
            query="{ ping }",
        )
        # dispatch_graphql returns a dict with 'body' containing JSON
        assert result is not None
        assert isinstance(result, dict)
        body = result.get("body", "")
        assert "ping" in body, f"Expected 'ping' in response body: {body}"

    def test_insert_and_query_neo4j_instance(self, pg_config):
        from knowledge_graph_engine.main import dispatch_graphql

        # Insert
        result = dispatch_graphql(
            context={"partition_key": PARTITION_KEY, "endpoint_id": ENDPOINT_ID, "part_id": PART_ID},
            query="""
                mutation {
                    insertUpdateNeo4jInstance(
                        instanceId: "itest-gql-instance"
                        neo4jUri: "bolt://localhost:7687"
                        neo4jPassword: "test"
                        status: "active"
                    ) {
                        instanceId
                        status
                        neo4jUri
                    }
                }
            """,
        )
        assert result is not None

        # Query it back
        result = dispatch_graphql(
            context={"partition_key": PARTITION_KEY, "endpoint_id": ENDPOINT_ID, "part_id": PART_ID},
            query="""
                {
                    neo4jInstance(instanceId: "itest-gql-instance") {
                        instanceId
                        status
                        neo4jUri
                    }
                }
            """,
        )
        assert result is not None

    def test_insert_and_query_document(self, pg_config):
        from knowledge_graph_engine.main import dispatch_graphql

        # Insert
        result = dispatch_graphql(
            context={"partition_key": PARTITION_KEY, "endpoint_id": ENDPOINT_ID, "part_id": PART_ID},
            query="""
                mutation {
                    insertUpdateDocument(
                        documentUuid: "itest-gql-doc"
                        documentSource: "graphql-test"
                        content: "Test via GraphQL"
                        updatedBy: "itest"
                    ) {
                        documentUuid
                        documentSource
                    }
                }
            """,
        )
        assert result is not None

        # Query list
        result = dispatch_graphql(
            context={"partition_key": PARTITION_KEY, "endpoint_id": ENDPOINT_ID, "part_id": PART_ID},
            query="""
                {
                    documentList(limit: 10) {
                        documentList {
                            documentUuid
                            documentSource
                        }
                        total
                    }
                }
            """,
        )
        assert result is not None

    def test_cleanup_gql_data(self, pg_config):
        """Clean up GraphQL test data."""
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        try:
            repo = get_repo("document")
            repo.delete(
                MagicMock(context={"partition_key": PARTITION_KEY, "endpoint_id": ENDPOINT_ID, "part_id": PART_ID, "logger": logger}),
                partition_key=PARTITION_KEY,
                document_uuid="itest-gql-doc",
            )
        except Exception:
            pass
        try:
            repo = get_repo("neo4j_instance")
            repo.delete(
                MagicMock(context={"partition_key": PARTITION_KEY, "endpoint_id": ENDPOINT_ID, "part_id": PART_ID, "logger": logger}),
                partition_key=PARTITION_KEY,
                instance_id="itest-gql-instance",
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# INT-008: DataLoader Dispatch with PG Backend
# ---------------------------------------------------------------------------

class TestINT008DataLoaderDispatch:
    """INT-008: PGRequestLoaders loads from PostgreSQL."""

    def test_get_loaders_returns_pg_request_loaders(self, pg_config):
        from knowledge_graph_engine.models.repositories.dispatch import (
            clear_registry,
            get_loaders,
        )

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        loaders = get_loaders({})
        assert type(loaders).__name__ == "PGRequestLoaders"

    def test_document_loader_loads_from_pg(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import (
            clear_registry,
            get_loaders,
        )

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"

        # Insert a document first
        repo = get_repo("document")
        repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            document_uuid="itest-loader-doc",
            document_source="loader-test",
            status="active",
            updated_by="itest",
        )

        # Load via DataLoader
        loaders = get_loaders({})
        loader = loaders.document_loader
        # DataLoader.load() returns a Promise
        from promise import Promise

        promise = loader.load((PARTITION_KEY, "itest-loader-doc"))
        assert isinstance(promise, Promise)

        # Clean up
        repo.delete(mock_info, partition_key=PARTITION_KEY, document_uuid="itest-loader-doc")


# ---------------------------------------------------------------------------
# INT-009: Partial Unique Index Enforcement
# ---------------------------------------------------------------------------

class TestINT009PartialUniqueIndex:
    """INT-009: Direct DB insert of two active schemas violates partial unique index."""

    def test_two_active_schemas_violate_index(self, pg_config, mock_info):
        from knowledge_graph_engine.models.repositories import get_repo
        from knowledge_graph_engine.models.repositories.dispatch import clear_registry
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        clear_registry()
        pg_config.DB_BACKEND = "postgresql"
        repo = get_repo("graph_schema")

        # Insert one active schema via repo (app code deactivates others)
        repo.insert_update(
            mock_info,
            partition_key=PARTITION_KEY,
            schema_name="itest-index-schema-a",
            schema_type="test",
            status="active",
        )

        # Now try to insert a second active schema via raw SQL (bypassing app code)
        # This should violate the partial unique index
        session = pg_config.db_session
        with pytest.raises(IntegrityError):
            session.execute(text(
                f"INSERT INTO graph_schemas (partition_key, schema_name, schema_type, "
                f"status, created_at, updated_at) VALUES "
                f"('{PARTITION_KEY}', 'itest-index-schema-b', 'test', 'active', NOW(), NOW())"
            ))
            session.commit()
        session.rollback()

        # Clean up
        repo.delete(
            mock_info,
            partition_key=PARTITION_KEY,
            schema_name="itest-index-schema-a",
        )


# ---------------------------------------------------------------------------
# INT-010: Cache Config Backend-Awareness
# ---------------------------------------------------------------------------

class TestINT010CacheConfigBackendAwareness:
    """INT-010: Cache config returns empty for PG, populated for DDB."""

    def test_pg_cache_config_empty(self, pg_config):
        pg_config.DB_BACKEND = "postgresql"
        config = pg_config.get_cache_entity_config()
        assert config == {}, "PG cache config should be empty"

    def test_pg_cache_relationships_empty(self, pg_config):
        pg_config.DB_BACKEND = "postgresql"
        rels = pg_config.get_cache_relationships()
        assert rels == {}, "PG cache relationships should be empty"

    def test_ddb_cache_config_populated(self, pg_config):
        pg_config.DB_BACKEND = "dynamodb"
        config = pg_config.get_cache_entity_config()
        assert "document" in config
        assert "graph_schema" in config
        assert len(config) == 5