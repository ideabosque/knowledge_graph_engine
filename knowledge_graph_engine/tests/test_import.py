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
        assert hasattr(Config, "DB_BACKEND")
        assert hasattr(Config, "db_session")


@pytest.mark.unit
class TestLazyModelImports:
    """Verify models/dynamodb/__init__.py lazy imports work."""

    def test_models_package_importable(self):
        import knowledge_graph_engine.models
        # Should not raise

    def test_dynamodb_models_package_importable(self):
        import knowledge_graph_engine.models.dynamodb
        # Should not raise

    def test_individual_model_import(self):
        from knowledge_graph_engine.models.dynamodb.graph_schema import GraphSchemaModel
        assert GraphSchemaModel is not None

    def test_lazy_getattr(self):
        from knowledge_graph_engine.models import dynamodb
        # Accessing a model name triggers lazy import
        assert hasattr(dynamodb, "GraphSchemaModel")


@pytest.mark.unit
class TestHandlerImports:
    """Verify handler modules are importable without side effects."""

    def test_import_schema_resolver(self):
        from knowledge_graph_engine.handlers.schema_resolution.handler import SchemaResolver
        assert SchemaResolver is not None

    def test_import_extractor(self):
        from knowledge_graph_engine.handlers.extraction.handler import Extractor
        assert Extractor is not None

    def test_import_search_handler(self):
        from knowledge_graph_engine.handlers.search.handler import SearchHandler
        assert SearchHandler is not None

    def test_import_rag_handler(self):
        from knowledge_graph_engine.handlers.search.handler import RAGHandler
        assert RAGHandler is not None


@pytest.mark.unit
class TestRepositoryDispatch:
    """Verify the repository dispatch boundary is importable."""

    def test_import_repositories(self):
        from knowledge_graph_engine.models.repositories import (
            get_repo,
            get_loaders,
            clear_registry,
            EntityRepository,
        )
        assert get_repo is not None
        assert get_loaders is not None
        assert clear_registry is not None
        assert EntityRepository is not None