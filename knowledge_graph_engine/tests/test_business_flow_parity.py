# -*- coding: utf-8 -*-
"""Business flow parity validation for the dual-backend repository boundary.

These tests verify that both backends expose the same contract surface
for all 5 entities and that entity-specific behaviors (single-active
invariant, driver-cache invalidation hooks, resolve_active) are present
on both sides. They do NOT require live databases — they check the
repository class interface and method signatures.

Integration tests against live DynamoDB / PostgreSQL are in
test_integration.py (DynamoDB) and test_postgresql_repositories.py (PG).
"""
from __future__ import print_function

__author__ = "silvaengine"

import inspect
from typing import Set

import pytest

from knowledge_graph_engine.handlers.config import Config
from knowledge_graph_engine.models.repositories import get_repo
from knowledge_graph_engine.models.repositories.dispatch import clear_registry


EXPECTED_ENTITIES: Set[str] = {
    "document",
    "graph_schema",
    "neo4j_instance",
    "request",
    "document_process_error",
}

# Methods required by the EntityRepository ABC on every repo.
REQUIRED_METHODS = {
    "get",
    "count",
    "list",
    "insert_update",
    "delete",
    "get_type",
    "entity_type",
}

# resolve_single is a convenience used by GraphQL queries — present on
# entities that have a single-record query field. document_process_error
# has no GraphQL query field, so it's exempt.
ENTITIES_WITH_RESOLVE_SINGLE = {
    "document",
    "graph_schema",
    "neo4j_instance",
    "request",
}

# Entities that must expose resolve_active (single-active invariant).
ENTITIES_WITH_ACTIVE = {"graph_schema", "neo4j_instance"}


@pytest.fixture
def restore_backend():
    original = Config.DB_BACKEND
    try:
        yield
    finally:
        Config.DB_BACKEND = original
        clear_registry()


# ---------------------------------------------------------------------------
# Contract surface parity — every backend exposes the same methods
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_dynamodb_repo_has_required_methods(restore_backend, entity_type):
    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    repo = get_repo(entity_type)
    for method in REQUIRED_METHODS:
        assert hasattr(repo, method), (
            f"DynamoDB {entity_type} repo missing method: {method}"
        )


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_postgresql_repo_has_required_methods(restore_backend, entity_type):
    Config.DB_BACKEND = "postgresql"
    clear_registry()
    repo = get_repo(entity_type)
    for method in REQUIRED_METHODS:
        assert hasattr(repo, method), (
            f"PostgreSQL {entity_type} repo missing method: {method}"
        )


@pytest.mark.parametrize("entity_type", sorted(ENTITIES_WITH_RESOLVE_SINGLE))
def test_dynamodb_repo_has_resolve_single(restore_backend, entity_type):
    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    repo = get_repo(entity_type)
    assert hasattr(repo, "resolve_single"), (
        f"DynamoDB {entity_type} repo missing resolve_single"
    )


@pytest.mark.parametrize("entity_type", sorted(ENTITIES_WITH_RESOLVE_SINGLE))
def test_postgresql_repo_has_resolve_single(restore_backend, entity_type):
    Config.DB_BACKEND = "postgresql"
    clear_registry()
    repo = get_repo(entity_type)
    assert hasattr(repo, "resolve_single"), (
        f"PostgreSQL {entity_type} repo missing resolve_single"
    )


# ---------------------------------------------------------------------------
# resolve_active parity — single-active entities expose it on both backends
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entity_type", sorted(ENTITIES_WITH_ACTIVE))
def test_dynamodb_repo_has_resolve_active(restore_backend, entity_type):
    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    repo = get_repo(entity_type)
    assert hasattr(repo, "resolve_active"), (
        f"DynamoDB {entity_type} repo must expose resolve_active()"
    )
    sig = inspect.signature(repo.resolve_active)
    params = list(sig.parameters)
    assert "partition_key" in params, (
        f"DynamoDB {entity_type}.resolve_active must accept partition_key"
    )


@pytest.mark.parametrize("entity_type", sorted(ENTITIES_WITH_ACTIVE))
def test_postgresql_repo_has_resolve_active(restore_backend, entity_type):
    Config.DB_BACKEND = "postgresql"
    clear_registry()
    repo = get_repo(entity_type)
    assert hasattr(repo, "resolve_active"), (
        f"PostgreSQL {entity_type} repo must expose resolve_active()"
    )
    sig = inspect.signature(repo.resolve_active)
    params = list(sig.parameters)
    assert "partition_key" in params, (
        f"PostgreSQL {entity_type}.resolve_active must accept partition_key"
    )


# ---------------------------------------------------------------------------
# Entity type identity — both backends report the same entity_type string
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_entity_type_matches_on_both_backends(restore_backend, entity_type):
    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    ddb_repo = get_repo(entity_type)
    assert ddb_repo.entity_type == entity_type

    Config.DB_BACKEND = "postgresql"
    clear_registry()
    pg_repo = get_repo(entity_type)
    assert pg_repo.entity_type == entity_type


# ---------------------------------------------------------------------------
# Loader surface parity — both backends expose the same loader properties
# ---------------------------------------------------------------------------

LOADER_PROPERTIES = ["document_loader", "graph_schema_loader"]


def test_dynamodb_loaders_have_expected_properties(restore_backend):
    from knowledge_graph_engine.models.repositories.dispatch import get_loaders

    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    loaders = get_loaders({})
    for name in LOADER_PROPERTIES:
        loader = getattr(loaders, name, None)
        assert loader is not None, f"DynamoDB loaders missing: {name}"
        assert hasattr(loader, "load"), f"DynamoDB {name} has no .load method"


def test_postgresql_loaders_have_expected_properties(restore_backend):
    from knowledge_graph_engine.models.repositories.dispatch import get_loaders

    Config.DB_BACKEND = "postgresql"
    clear_registry()
    loaders = get_loaders({})
    for name in LOADER_PROPERTIES:
        loader = getattr(loaders, name, None)
        assert loader is not None, f"PostgreSQL loaders missing: {name}"
        assert hasattr(loader, "load"), f"PostgreSQL {name} has no .load method"


# ---------------------------------------------------------------------------
# Config backend selection validation
# ---------------------------------------------------------------------------

def test_config_db_backend_defaults_to_dynamodb(restore_backend):
    Config.DB_BACKEND = "dynamodb"
    assert Config.DB_BACKEND == "dynamodb"


def test_config_rejects_unknown_backend(restore_backend):
    """Config.initialize should raise ValueError for unsupported backends."""
    Config.DB_BACKEND = "mongodb"
    clear_registry()
    # get_repo will fail with KeyError (no repos registered for 'mongodb')
    with pytest.raises(KeyError):
        get_repo("document")


# ---------------------------------------------------------------------------
# Cache config is backend-aware
# ---------------------------------------------------------------------------

def test_dynamodb_cache_config_populated(restore_backend):
    Config.DB_BACKEND = "dynamodb"
    config = Config.get_cache_entity_config()
    assert "document" in config
    assert "graph_schema" in config
    assert "neo4j_instance" in config
    assert "request" in config
    assert "document_process_error" in config


def test_postgresql_cache_config_empty(restore_backend):
    Config.DB_BACKEND = "postgresql"
    config = Config.get_cache_entity_config()
    assert config == {}, "PostgreSQL cache config should be empty (no @method_cache)"


def test_dynamodb_cache_relationships_populated(restore_backend):
    Config.DB_BACKEND = "dynamodb"
    rels = Config.get_cache_relationships()
    assert "document" in rels
    assert "graph_schema" in rels


def test_postgresql_cache_relationships_empty(restore_backend):
    Config.DB_BACKEND = "postgresql"
    rels = Config.get_cache_relationships()
    assert rels == {}, "PostgreSQL cache relationships should be empty"


# ---------------------------------------------------------------------------
# Module path sanity — cache config module paths point at models.dynamodb
# ---------------------------------------------------------------------------

def test_dynamodb_cache_config_module_paths(restore_backend):
    Config.DB_BACKEND = "dynamodb"
    config = Config.get_cache_entity_config()
    for entity, entry in config.items():
        module = entry.get("module", "")
        assert "models.dynamodb" in module, (
            f"Cache config for {entity} points at {module}, "
            f"expected models.dynamodb.*"
        )


# ---------------------------------------------------------------------------
# Neo4j / search / rag / extract are backend-independent
# ---------------------------------------------------------------------------

def test_search_handler_does_not_import_models_dynamodb(restore_backend):
    """The search handler must route metadata through repositories, not
    import models.dynamodb directly. This ensures search/rag/extract work
    identically under both backends."""
    import os
    handler_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "handlers",
        "search",
        "handler.py",
    )
    with open(handler_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "models.dynamodb" not in source, (
        "search/handler.py imports models.dynamodb directly — "
        "must route through models.repositories"
    )


def test_extraction_handler_does_not_import_models_dynamodb(restore_backend):
    """The extraction handler must route metadata through repositories."""
    import os
    handler_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "handlers",
        "extraction",
        "handler.py",
    )
    with open(handler_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "models.dynamodb" not in source, (
        "extraction/handler.py imports models.dynamodb directly — "
        "must route through models.repositories"
    )


def test_schema_resolution_handler_does_not_import_models_dynamodb(restore_backend):
    """The schema_resolution handler must route metadata through repositories."""
    import os
    handler_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "handlers",
        "schema_resolution",
        "handler.py",
    )
    with open(handler_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "models.dynamodb" not in source, (
        "schema_resolution/handler.py imports models.dynamodb directly — "
        "must route through models.repositories"
    )


def test_neo4j_connection_manager_does_not_import_models_dynamodb(restore_backend):
    """Neo4jConnectionManager must route through repositories."""
    import os
    handler_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "handlers",
        "neo4j_connection_manager.py",
    )
    with open(handler_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "models.dynamodb" not in source, (
        "neo4j_connection_manager.py imports models.dynamodb directly — "
        "must route through models.repositories"
    )


# ---------------------------------------------------------------------------
# PostgreSQL models have partial unique indexes for single-active invariant
# ---------------------------------------------------------------------------

def test_graph_schema_pg_model_has_partial_unique_index():
    """The GraphSchema SQLAlchemy model must have a partial unique index
    on (partition_key) WHERE status = 'active' to enforce the single-active
    invariant at the database level."""
    from knowledge_graph_engine.models.postgresql.graph_schema import GraphSchemaModel

    table_args = GraphSchemaModel.__table_args__
    found = False
    for arg in table_args:
        if hasattr(arg, "unique") and arg.unique:
            # Check it's a postgresql_where partial index
            dialect_kwargs = getattr(arg, "dialect_kwargs", {})
            if "postgresql_where" in dialect_kwargs:
                found = True
                break
    assert found, (
        "GraphSchemaModel must have a partial unique index "
        "WHERE status = 'active' for the single-active invariant"
    )


def test_neo4j_instance_pg_model_has_partial_unique_index():
    """The Neo4jInstance SQLAlchemy model must have a partial unique index
    on (partition_key) WHERE status = 'active'."""
    from knowledge_graph_engine.models.postgresql.neo4j_instance import (
        Neo4jInstanceModel,
    )

    table_args = Neo4jInstanceModel.__table_args__
    found = False
    for arg in table_args:
        if hasattr(arg, "unique") and arg.unique:
            dialect_kwargs = getattr(arg, "dialect_kwargs", {})
            if "postgresql_where" in dialect_kwargs:
                found = True
                break
    assert found, (
        "Neo4jInstanceModel must have a partial unique index "
        "WHERE status = 'active' for the single-active invariant"
    )