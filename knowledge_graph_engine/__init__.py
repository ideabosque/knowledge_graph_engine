#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from ._compat import (
    ensure_neo4j_compat,
    ensure_neo4j_graphrag_compat,
    ensure_silvaengine_dynamodb_base_compat,
    ensure_silvaengine_utility_compat,
)

ensure_neo4j_compat()
ensure_neo4j_graphrag_compat()
ensure_silvaengine_dynamodb_base_compat()
ensure_silvaengine_utility_compat()

__all__ = ["KnowledgeGraphEngine", "deploy"]


def __getattr__(name):
    """
    Lazily import heavy runtime entrypoints so helper modules remain importable
    in partial environments and unit tests.
    """
    if name in __all__:
        from .main import KnowledgeGraphEngine, deploy

        exports = {
            "KnowledgeGraphEngine": KnowledgeGraphEngine,
            "deploy": deploy,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
