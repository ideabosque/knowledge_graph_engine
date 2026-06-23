# -*- coding: utf-8 -*-
"""Backend-agnostic repository dispatch contract tests.

These tests verify that the repository dispatch boundary exposes a uniform
contract across both backends for all 5 persisted entities:

* ``get_repo(entity_type)`` resolves to a registered repository whose
  ``entity_type`` matches the requested key, for both ``dynamodb`` and
  ``postgresql``.
* ``get_loaders(context)`` returns the backend-appropriate request-scoped
  loaders (``RequestLoaders`` vs ``PGRequestLoaders``).
* The set of registered entity types is identical on both backends.

These tests do not require any external service: they exercise registration
and dispatch only.
"""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Dict, Set

import pytest

from knowledge_graph_engine.handlers.config import Config
from knowledge_graph_engine.models.repositories.dispatch import (
    clear_registry,
    get_loaders,
    get_repo,
)


# The 5 persisted entities the dual-backend structure must cover.
EXPECTED_ENTITIES: Set[str] = {
    "document",
    "graph_schema",
    "neo4j_instance",
    "request",
    "document_process_error",
}


@pytest.fixture
def restore_backend():
    """Snapshot and restore ``Config.DB_BACKEND`` + registry around each test."""
    original = Config.DB_BACKEND
    try:
        yield
    finally:
        Config.DB_BACKEND = original
        clear_registry()


def _registered_entities(backend: str) -> Dict[str, str]:
    """Force registration for ``backend`` and return {entity_type: repo_class}."""
    from knowledge_graph_engine.models.repositories import dispatch as dispatch_mod

    if backend == "dynamodb":
        dispatch_mod._init_dynamodb_repos()
        return {
            et: type(r).__name__
            for et, r in dispatch_mod._repo_registry["dynamodb"].items()
        }
    if backend == "postgresql":
        dispatch_mod._init_postgresql_repos()
        return {
            et: type(r).__name__
            for et, r in dispatch_mod._repo_registry["postgresql"].items()
        }
    raise ValueError(f"Unknown backend: {backend}")


def test_dynamodb_registers_all_expected_entities(restore_backend):
    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    registered = set(_registered_entities("dynamodb").keys())
    missing = EXPECTED_ENTITIES - registered
    assert not missing, f"DynamoDB registry missing entities: {sorted(missing)}"


def test_postgresql_registers_all_expected_entities(restore_backend):
    Config.DB_BACKEND = "postgresql"
    clear_registry()
    registered = set(_registered_entities("postgresql").keys())
    missing = EXPECTED_ENTITIES - registered
    assert not missing, f"PostgreSQL registry missing entities: {sorted(missing)}"


def test_both_backends_register_identical_entity_sets(restore_backend):
    """Switching backends must not silently drop any entity."""
    clear_registry()
    ddb = set(_registered_entities("dynamodb").keys())
    pg = set(_registered_entities("postgresql").keys())
    assert ddb == pg == EXPECTED_ENTITIES, (
        f"Entity set mismatch. DynamoDB-only: {sorted(ddb - pg)}, "
        f"PostgreSQL-only: {sorted(pg - ddb)}"
    )


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_get_repo_resolves_dynamodb(restore_backend, entity_type):
    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    repo = get_repo(entity_type)
    assert repo is not None
    assert repo.entity_type == entity_type


@pytest.mark.parametrize("entity_type", sorted(EXPECTED_ENTITIES))
def test_get_repo_resolves_postgresql(restore_backend, entity_type):
    Config.DB_BACKEND = "postgresql"
    clear_registry()
    repo = get_repo(entity_type)
    assert repo is not None
    assert repo.entity_type == entity_type


def test_get_repo_raises_keyerror_for_unknown_entity(restore_backend):
    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    with pytest.raises(KeyError):
        get_repo("nonexistent_entity")


def test_get_repo_raises_for_unknown_backend(restore_backend):
    Config.DB_BACKEND = "mongodb"
    clear_registry()
    with pytest.raises(KeyError):
        get_repo("document")


def test_get_loaders_returns_request_loaders_for_dynamodb(restore_backend):
    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    loaders = get_loaders({})
    assert type(loaders).__name__ == "RequestLoaders"


def test_get_loaders_returns_pg_request_loaders_for_postgresql(restore_backend):
    Config.DB_BACKEND = "postgresql"
    clear_registry()
    loaders = get_loaders({})
    assert type(loaders).__name__ == "PGRequestLoaders"


def test_get_loaders_raises_for_unknown_backend(restore_backend):
    Config.DB_BACKEND = "mongodb"
    clear_registry()
    with pytest.raises(ValueError):
        get_loaders({})


def test_get_loaders_is_memoized_on_context(restore_backend):
    Config.DB_BACKEND = "dynamodb"
    clear_registry()
    context: Dict[str, object] = {}
    first = get_loaders(context)
    second = get_loaders(context)
    assert first is second
    assert context["batch_loaders"] is first