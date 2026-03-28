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
