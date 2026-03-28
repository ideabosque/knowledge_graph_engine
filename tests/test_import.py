# -*- coding: utf-8 -*-
"""
Import smoke tests — verify the package is importable in a clean environment.
These tests should pass without any external services (Neo4j, DynamoDB, etc.).

Run with: pytest tests/test_import.py -v
"""
from __future__ import print_function

import pytest


@pytest.mark.unit
class TestPackageImport:
    """Verify top-level imports succeed without triggering heavy dependency chains."""

    def test_import_package(self):
        import knowledge_graph_engine

    def test_import_engine_class(self):
        from knowledge_graph_engine.main import KnowledgeGraphEngine
        assert KnowledgeGraphEngine is not None

    def test_import_deploy(self):
        from knowledge_graph_engine import deploy
        assert callable(deploy)

    def test_import_partition_manager(self):
        from knowledge_graph_engine.handlers.partition_manager import PartitionManager
        assert hasattr(PartitionManager, "build_partition_key")

    def test_import_config(self):
        from knowledge_graph_engine.handlers.config import Config
        assert Config is not None


@pytest.mark.unit
class TestLazyModelImports:
    """Verify models/__init__.py does not eagerly pull in all models."""

    def test_models_package_importable(self):
        import knowledge_graph_engine.models
        # Should not raise — lazy __getattr__ means no eager model loading

    def test_individual_model_import(self):
        from knowledge_graph_engine.models.graph_schema import GraphSchemaModel
        assert GraphSchemaModel is not None

    def test_lazy_getattr(self):
        from knowledge_graph_engine import models
        # Accessing a model name triggers lazy import
        assert hasattr(models, "GraphSchemaModel")


@pytest.mark.unit
class TestHandlerImports:
    """Verify handler modules are importable without side effects."""

    def test_import_schema_resolver(self):
        from knowledge_graph_engine.handlers.schema_resolver import SchemaResolver
        assert SchemaResolver is not None

    def test_import_extractor(self):
        from knowledge_graph_engine.handlers.extractor import Extractor
        assert Extractor is not None

    def test_import_search_handler(self):
        from knowledge_graph_engine.handlers.search_handler import SearchHandler
        assert SearchHandler is not None

    def test_import_rag_handler(self):
        from knowledge_graph_engine.handlers.rag_handler import RAGHandler
        assert RAGHandler is not None
