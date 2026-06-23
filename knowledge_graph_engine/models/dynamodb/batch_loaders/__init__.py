# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict

from .base import SafeDataLoader
from .document_loader import DocumentLoader
from .graph_schema_loader import GraphSchemaLoader


class RequestLoaders:
    """Container for all batch loaders in a single request."""

    def __init__(self, context: Dict[str, Any], cache_enabled: bool = True):
        logger = context.get("logger")
        self.cache_enabled = cache_enabled

        self.document_loader = DocumentLoader(logger=logger, cache_enabled=cache_enabled)
        self.graph_schema_loader = GraphSchemaLoader(logger=logger, cache_enabled=cache_enabled)


def get_loaders(context: Dict[str, Any]) -> RequestLoaders:
    """Get or create request loaders from context."""
    if context is None:
        context = {}

    loaders = context.get("batch_loaders")
    if loaders is not None:
        return loaders

    from ....handlers.config import Config

    cache_enabled = Config.is_cache_enabled()
    loaders = RequestLoaders(context, cache_enabled=cache_enabled)
    context["batch_loaders"] = loaders
    return loaders


def clear_loaders(context: Dict[str, Any]) -> None:
    """Clear loaders from context (useful for tests)."""
    if context is None:
        return
    context.pop("batch_loaders", None)


__all__ = [
    "RequestLoaders",
    "get_loaders",
    "clear_loaders",
    "DocumentLoader",
    "GraphSchemaLoader",
]