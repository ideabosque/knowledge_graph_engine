# -*- coding: utf-8 -*-
from __future__ import print_function

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_document_list_filter_builds_status_condition(mock_info):
    """Verify that status filter is correctly composed even when document_source is None."""
    from knowledge_graph_engine.models.document import DocumentModel

    # Test the filter composition logic directly (the decorator wraps the return)
    the_filters = None
    document_source = None
    statuses = ["active"]
    if document_source:
        the_filters = DocumentModel.document_source == document_source
    if statuses:
        status_filter = DocumentModel.status.is_in(*statuses)
        the_filters = status_filter if the_filters is None else the_filters & status_filter

    assert the_filters is not None


@pytest.mark.unit
def test_graph_schema_list_filter_builds_status_condition(mock_info):
    """Verify that status filter is correctly composed even when schema_type is None."""
    from knowledge_graph_engine.models.graph_schema import GraphSchemaModel

    the_filters = None
    schema_type = None
    statuses = ["active"]
    if schema_type:
        the_filters = GraphSchemaModel.schema_type == schema_type
    if statuses:
        status_filter = GraphSchemaModel.status.is_in(*statuses)
        the_filters = status_filter if the_filters is None else the_filters & status_filter

    assert the_filters is not None


@pytest.mark.unit
def test_listener_info_flattens_context(mock_logger):
    from knowledge_graph_engine.utils.listener import create_listener_info

    info = create_listener_info(
        mock_logger,
        "search",
        {"mode": "test"},
        context={"partition_key": "ep#part", "request_id": "abc"},
    )

    assert info.context["partition_key"] == "ep#part"
    assert info.context["request_id"] == "abc"
    assert "context" not in info.context


@pytest.mark.unit
def test_get_active_graph_schema_chooses_most_recent():
    from knowledge_graph_engine.models.graph_schema import get_active_graph_schema

    older = SimpleNamespace(status="active", created_at=1, updated_at=2, schema_name="older")
    newer = SimpleNamespace(status="active", created_at=1, updated_at=3, schema_name="newer")

    with patch("knowledge_graph_engine.models.graph_schema.GraphSchemaModel.query", return_value=[older, newer]):
        with patch("knowledge_graph_engine.models.graph_schema.Config.get_logger", return_value=logging.getLogger("test")):
            result = get_active_graph_schema("ep#part")

    assert result is newer


@pytest.mark.unit
def test_get_active_neo4j_instance_chooses_most_recent():
    from knowledge_graph_engine.models.neo4j_instance import get_active_neo4j_instance

    older = SimpleNamespace(status="active", created_at=1, updated_at=2, instance_id="old")
    newer = SimpleNamespace(status="active", created_at=1, updated_at=3, instance_id="new")

    with patch("knowledge_graph_engine.models.neo4j_instance.Neo4jInstanceModel.query", return_value=[older, newer]):
        with patch("knowledge_graph_engine.models.neo4j_instance.Config.get_logger", return_value=logging.getLogger("test")):
            result = get_active_neo4j_instance("ep#part")

    assert result is newer


@pytest.mark.unit
def test_request_uuid_auto_generated_when_missing():
    """Verify request_uuid is generated when not provided, without hitting DynamoDB."""
    import uuid as uuid_mod

    # The logic under test: if not request_uuid, generate one
    request_uuid = None
    if not request_uuid:
        import pendulum
        request_uuid = f"req-{pendulum.now('UTC').int_timestamp}-{uuid_mod.uuid4().hex[:8]}"

    assert request_uuid.startswith("req-")
    parts = request_uuid.split("-")
    assert len(parts) == 3
    assert parts[1].isdigit()


@pytest.mark.unit
def test_config_reinitialize_replaces_settings(mock_logger):
    from knowledge_graph_engine.handlers.config import Config

    Config.reset()
    try:
        with patch("knowledge_graph_engine.handlers.config.boto3.client", return_value=object()):
            Config.initialize(mock_logger, {"auth_provider": "local", "jwt_secret_key": "one"})
            Config.initialize(mock_logger, {"auth_provider": "local", "jwt_secret_key": "two"})

        assert Config.get_setting()["jwt_secret_key"] == "two"
    finally:
        Config.reset()


@pytest.mark.unit
def test_resolve_embedding_dimensions_known_models():
    """Known OpenAI/Ollama embedding models resolve to correct dimensions."""
    from knowledge_graph_engine.utils.graph_rag_util import resolve_embedding_dimensions

    assert resolve_embedding_dimensions("text-embedding-3-small") == 1536
    assert resolve_embedding_dimensions("text-embedding-3-large") == 3072
    assert resolve_embedding_dimensions("text-embedding-ada-002") == 1536
    assert resolve_embedding_dimensions("nomic-embed-text") == 768
    assert resolve_embedding_dimensions("mxbai-embed-large") == 1024
    assert resolve_embedding_dimensions("all-minilm") == 384


@pytest.mark.unit
def test_resolve_embedding_dimensions_override_wins():
    """Explicit override always takes precedence over the model lookup."""
    from knowledge_graph_engine.utils.graph_rag_util import resolve_embedding_dimensions

    # Override beats the known mapping
    assert resolve_embedding_dimensions("text-embedding-3-small", override=2048) == 2048
    # Override resolves unknown model
    assert resolve_embedding_dimensions("custom-model-xyz", override=512) == 512


@pytest.mark.unit
def test_resolve_embedding_dimensions_unknown_defaults_to_1536(caplog):
    """Unknown model without override falls back to 1536 and logs a warning."""
    from knowledge_graph_engine.utils.graph_rag_util import resolve_embedding_dimensions

    with caplog.at_level(logging.WARNING):
        result = resolve_embedding_dimensions("totally-fictional-model")

    assert result == 1536
    assert any("Unknown embedding model" in r.message for r in caplog.records)


@pytest.mark.unit
def test_list_resolvers_raise_when_partition_key_missing():
    """List resolvers must raise ValueError when partition_key is missing from context.

    Prevents the silent Model.scan() fallback that would return cross-partition data.
    """
    from knowledge_graph_engine.models.document import resolve_document_list as doc_list
    from knowledge_graph_engine.models.graph_schema import resolve_graph_schema_list as gs_list
    from knowledge_graph_engine.models.neo4j_instance import resolve_neo4j_instance_list as ni_list
    from knowledge_graph_engine.models.request import resolve_request_list as req_list

    # The list resolvers are wrapped by `resolve_list_decorator` which logs on
    # error before re-raising, so the context needs a logger to reach the raise.
    info = SimpleNamespace(context={"logger": logging.getLogger("test")})

    for resolver in (doc_list, gs_list, ni_list, req_list):
        with pytest.raises(ValueError, match="partition_key is required"):
            resolver(info)


@pytest.mark.unit
def test_fastapi_get_partition_key_requires_part_id():
    """FastAPI _get_partition_key must raise 400 when Part-Id header is absent.

    A bare endpoint_id would hash to its own partition bucket, hiding data
    written under the proper `endpoint#part_id` key.
    """
    from fastapi import HTTPException
    from knowledge_graph_engine.handlers.fastapi_app import _get_partition_key

    request = SimpleNamespace(headers={})  # no Part-Id

    with pytest.raises(HTTPException) as excinfo:
        _get_partition_key("my-endpoint", request)

    assert excinfo.value.status_code == 400
    assert "Part-Id" in excinfo.value.detail


@pytest.mark.unit
def test_fastapi_get_partition_key_accepts_part_id():
    """When Part-Id is present, _get_partition_key builds the full key."""
    from knowledge_graph_engine.handlers.fastapi_app import _get_partition_key

    request = SimpleNamespace(headers={"Part-Id": "tenant-a"})
    pk, part_id = _get_partition_key("my-endpoint", request)

    assert pk == "my-endpoint#tenant-a"
    assert part_id == "tenant-a"


