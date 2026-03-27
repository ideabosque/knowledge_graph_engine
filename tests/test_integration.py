# -*- coding: utf-8 -*-
"""
Integration tests for Knowledge Graph Engine.
Requires valid AWS credentials and settings in .env file.
Run with: pytest tests/test_integration.py -m integration -v
"""
from __future__ import print_function

__author__ = "silvaengine"

import json

import pytest

from .conftest import SETTING


@pytest.mark.integration
class TestPingAndTables:
    """Test engine initialization, table creation, and ping query."""

    def test_ping(self, engine):
        """Test ping query returns successful response."""
        result = engine.knowledge_graph_engine_graphql(
            query="{ ping }",
            endpoint_id=SETTING.get("endpoint_id"),
            part_id=SETTING.get("part_id"),
        )

        assert result is not None
        assert result.get("statusCode") == 200

        body = result.get("body")
        if isinstance(body, str):
            body = json.loads(body)

        assert "data" in body
        assert "ping" in body["data"]
        assert body["data"]["ping"].startswith("Hello at ")

    def test_tables_created(self, engine):
        """Verify DynamoDB tables exist after engine initialization."""
        from knowledge_graph_engine.models.neo4j_instance import Neo4jInstanceModel
        from knowledge_graph_engine.models.document import DocumentModel
        from knowledge_graph_engine.models.graph_schema import GraphSchemaModel
        from knowledge_graph_engine.models.request import RequestModel
        from knowledge_graph_engine.models.document_process_error import DocumentProcessErrorModel

        models = [
            Neo4jInstanceModel,
            DocumentModel,
            GraphSchemaModel,
            RequestModel,
            DocumentProcessErrorModel,
        ]

        for model in models:
            assert model.exists(), f"Table {model.Meta.table_name} should exist"


@pytest.mark.integration
class TestNeo4jInstance:
    """Test Neo4j instance registration via GraphQL mutation."""

    def test_register_neo4j_instance(self, engine):
        """Register a Neo4j instance using .env settings."""
        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")

        neo4j_uri = SETTING.get("neo4j_uri")
        neo4j_password = SETTING.get("neo4j_password")
        assert neo4j_uri, "neo4j_uri must be set in .env"
        assert neo4j_password, "neo4j_password must be set in .env"

        from knowledge_graph_engine.handlers.partition_manager import PartitionManager

        partition_key = PartitionManager.build_partition_key(endpoint_id, part_id)

        mutation = """
            mutation(
                $partitionKey: String!,
                $instanceId: String,
                $neo4jUri: String!,
                $neo4jUsername: String,
                $neo4jPassword: String!,
                $neo4jDatabase: String
            ) {
                insertUpdateNeo4jInstance(
                    partitionKey: $partitionKey,
                    instanceId: $instanceId,
                    neo4jUri: $neo4jUri,
                    neo4jUsername: $neo4jUsername,
                    neo4jPassword: $neo4jPassword,
                    neo4jDatabase: $neo4jDatabase
                ) {
                    partitionKey
                    instanceId
                    neo4jUri
                    neo4jUsername
                    neo4jDatabase
                    status
                }
            }
        """

        variables = {
            "partitionKey": partition_key,
            "instanceId": "default",
            "neo4jUri": neo4j_uri,
            "neo4jUsername": SETTING.get("neo4j_username", "neo4j"),
            "neo4jPassword": neo4j_password,
            "neo4jDatabase": SETTING.get("neo4j_database", "neo4j"),
        }

        result = engine.knowledge_graph_engine_graphql(
            query=mutation,
            variables=variables,
            endpoint_id=endpoint_id,
            part_id=part_id,
        )

        assert result is not None
        assert result.get("statusCode") == 200, f"Expected 200, got: {result}"

        body = result.get("body")
        if isinstance(body, str):
            body = json.loads(body)

        data = body["data"]["insertUpdateNeo4jInstance"]
        assert data["partitionKey"] == partition_key
        assert data["instanceId"] == "default"
        assert data["neo4jUri"] == neo4j_uri
        assert data["neo4jDatabase"] == SETTING.get("neo4j_database", "neo4j")
        assert data["status"] == "active"

    def test_query_neo4j_instance(self, engine):
        """Verify the registered Neo4j instance can be queried back."""
        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")

        query = """
            query($instanceId: String!) {
                neo4jInstance(instanceId: $instanceId) {
                    partitionKey
                    instanceId
                    neo4jUri
                    neo4jUsername
                    neo4jDatabase
                    status
                }
            }
        """

        result = engine.knowledge_graph_engine_graphql(
            query=query,
            variables={"instanceId": "default"},
            endpoint_id=endpoint_id,
            part_id=part_id,
        )

        assert result is not None
        assert result.get("statusCode") == 200, f"Expected 200, got: {result}"

        body = result.get("body")
        if isinstance(body, str):
            body = json.loads(body)

        data = body["data"]["neo4jInstance"]
        assert data["neo4jUri"] == SETTING.get("neo4j_uri")
        assert data["status"] == "active"
