# -*- coding: utf-8 -*-
"""Smoke tests for dual-backend DataLoader dispatch."""
from __future__ import print_function

from knowledge_graph_engine.handlers.config import Config
from knowledge_graph_engine.models.repositories.dispatch import clear_registry, get_loaders


PG_LOADER_PROPERTIES = [
    "document_loader",
    "graph_schema_loader",
]


def test_get_loaders_dispatches_dynamodb_by_default():
    original_backend = Config.DB_BACKEND
    try:
        Config.DB_BACKEND = "dynamodb"
        clear_registry()
        loaders = get_loaders({})
        assert type(loaders).__name__ == "RequestLoaders"
    finally:
        Config.DB_BACKEND = original_backend
        clear_registry()


def test_postgresql_loader_surface_is_complete():
    original_backend = Config.DB_BACKEND
    try:
        Config.DB_BACKEND = "postgresql"
        clear_registry()
        loaders = get_loaders({})
        assert type(loaders).__name__ == "PGRequestLoaders"
        for name in PG_LOADER_PROPERTIES:
            loader = getattr(loaders, name)
            assert loader is not None, name
            assert hasattr(loader, "load"), name
    finally:
        Config.DB_BACKEND = original_backend
        clear_registry()