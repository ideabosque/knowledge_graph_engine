# -*- coding: utf-8 -*-
"""
Tests for knowledge_graph_engine extraction functionality.
"""
from __future__ import print_function

__author__ = "silvaengine"

import pytest
from unittest.mock import MagicMock, patch

# Import from parent package
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestExtractor:
    """Test knowledge graph extraction functionality."""

    @pytest.mark.unit
    def test_extractor_initialization(self, mock_info):
        """Test Extractor can be initialized."""
        from knowledge_graph_engine.handlers.extractor import Extractor

        extractor = Extractor(mock_info)
        assert extractor is not None
        assert extractor.info == mock_info

    @pytest.mark.unit
    def test_extract_requires_partition_key(self, mock_info):
        """Test that extract fails without partition_key."""
        from knowledge_graph_engine.handlers.extractor import Extractor

        extractor = Extractor(mock_info)
        with pytest.raises(ValueError, match="partition_key"):
            extractor.extract(text="test text")

    @pytest.mark.unit
    def test_extract_requires_text(self, mock_info):
        """Test that extract fails without text."""
        from knowledge_graph_engine.handlers.extractor import Extractor

        extractor = Extractor(mock_info)
        with pytest.raises(ValueError, match="text"):
            extractor.extract(partition_key="test#part")


class TestSchemaResolver:
    """Test schema resolution functionality."""

    @pytest.mark.unit
    def test_schema_resolver_initialization(self):
        """Test SchemaResolver can be initialized."""
        from knowledge_graph_engine.handlers.schema_resolver import SchemaResolver

        mock_graph_rag = MagicMock()
        resolver = SchemaResolver(mock_graph_rag, "test#part")
        assert resolver is not None
        assert resolver.partition_key == "test#part"

    @pytest.mark.unit
    def test_dict_to_graph_schema(self):
        """Test converting dict to GraphSchema."""
        from knowledge_graph_engine.handlers.schema_resolver import SchemaResolver
        from neo4j_graphrag.experimental.components.schema import NodeType, PropertyType

        mock_graph_rag = MagicMock()
        resolver = SchemaResolver(mock_graph_rag, "test#part")

        # Valid schema dict with node_types format (neo4j-graphrag-python API)
        schema_dict = {
            "node_types": [
                {
                    "label": "Company",
                    "properties": [{"name": "name", "type": "STRING"}]
                }
            ],
            "relationship_types": [
                {"label": "OWNS"}
            ],
            "patterns": [
                ["Company", "OWNS", "Company"]
            ]
        }

        result = resolver._dict_to_graph_schema(schema_dict)
        assert result is not None
        assert len(result.node_types) == 1
        assert result.node_types[0].label == "Company"

    @pytest.mark.unit
    def test_dict_to_graph_schema_with_strings(self):
        """Test converting dict with string node types to GraphSchema."""
        from knowledge_graph_engine.handlers.schema_resolver import SchemaResolver

        mock_graph_rag = MagicMock()
        resolver = SchemaResolver(mock_graph_rag, "test#part")

        # Schema with string node types (simplified format)
        schema_dict = {
            "node_types": ["Company", "Person"],
            "relationship_types": ["OWNS", "WORKS_AT"],
        }

        result = resolver._dict_to_graph_schema(schema_dict)
        assert result is not None
        assert len(result.node_types) == 2


class TestPartitionManager:
    """Test partition manager functionality."""

    @pytest.mark.unit
    def test_build_partition_key(self):
        """Test partition key building."""
        from knowledge_graph_engine.handlers.partition_manager import PartitionManager

        key = PartitionManager.build_partition_key("ep001", "partA")
        assert key == "ep001#partA"

    @pytest.mark.unit
    def test_parse_partition_key(self):
        """Test partition key parsing."""
        from knowledge_graph_engine.handlers.partition_manager import PartitionManager

        endpoint_id, part_id = PartitionManager.parse_partition_key("ep001#partA")
        assert endpoint_id == "ep001"
        assert part_id == "partA"


class TestNeo4jConnectionManager:
    """Test Neo4j connection manager functionality."""

    @pytest.mark.unit
    def test_connection_manager_initialization(self):
        """Test Neo4jConnectionManager can be initialized."""
        from knowledge_graph_engine.handlers.neo4j_connection_manager import Neo4jConnectionManager

        # Clear any existing drivers
        Neo4jConnectionManager._drivers = {}
        
        # Manager should be ready to create connections
        assert Neo4jConnectionManager._lock is not None

    @pytest.mark.unit
    def test_close_driver_removes_from_cache(self):
        """Test that close_driver removes driver from cache."""
        from knowledge_graph_engine.handlers.neo4j_connection_manager import Neo4jConnectionManager

        Neo4jConnectionManager._drivers = {}
        
        # Add a mock driver
        mock_driver = MagicMock()
        Neo4jConnectionManager._drivers["test#part"] = mock_driver
        
        # Close it
        Neo4jConnectionManager.close_driver("test#part")
        
        assert "test#part" not in Neo4jConnectionManager._drivers


class TestGraphRAGUtil:
    """Test GraphRAG utility functionality."""

    @pytest.mark.unit
    def test_graph_rag_util_initialization(self):
        """Test GraphRAGUtil can be initialized with settings."""
        from knowledge_graph_engine.utils.graph_rag_util import GraphRAGUtil

        mock_driver = MagicMock()
        settings = {
            "llm_type": "openai",
            "llm_name": "gpt-4o",
            "openai_api_key": "test-key",
        }

        # Patch OpenAILLM to avoid actual initialization
        with patch("knowledge_graph_engine.utils.graph_rag_util.OpenAILLM"):
            util = GraphRAGUtil(
                driver=mock_driver,
                neo4j_database="neo4j",
                settings=settings,
            )
            assert util.driver == mock_driver
            assert util.neo4j_database == "neo4j"