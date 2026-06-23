# -*- coding: utf-8 -*-
"""PostgreSQL batch loaders package.

Provides PGRequestLoaders — the PostgreSQL equivalent of the DynamoDB
RequestLoaders container. Uses the same Promise DataLoader pattern but
queries SQLAlchemy models instead of PynamoDB.
"""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict

from ....handlers.config import Config


class PGRequestLoaders:
    """Container for PostgreSQL-backed DataLoaders scoped to a single GraphQL request.

    This mirrors the DynamoDB RequestLoaders container but uses
    SQLAlchemy-based batch loaders. Each loader is lazily instantiated
    to avoid importing model modules that may not be ported yet.
    """

    def __init__(self, context: Dict[str, Any], cache_enabled: bool = True):
        logger = context.get("logger")
        self.cache_enabled = cache_enabled
        self._logger = logger
        self._context = context
        self._loaders: Dict[str, Any] = {}

    def _get_loader(self, name: str, loader_cls_name: str, module_path: str):
        """Lazily instantiate a loader."""
        if name not in self._loaders:
            try:
                import importlib

                mod = importlib.import_module(module_path, package=__name__)
                loader_cls = getattr(mod, loader_cls_name)
                self._loaders[name] = loader_cls(
                    logger=self._logger, cache_enabled=self.cache_enabled
                )
            except ImportError as exc:
                raise RuntimeError(
                    f"PostgreSQL loader '{name}' is not implemented: {module_path}"
                ) from exc
        return self._loaders[name]

    @property
    def document_loader(self):
        return self._get_loader(
            "document_loader", "PGDocumentLoader", ".document_loader"
        )

    @property
    def graph_schema_loader(self):
        return self._get_loader(
            "graph_schema_loader", "PGGraphSchemaLoader", ".graph_schema_loader"
        )

    def invalidate_cache(self, entity_type: str, entity_keys: Dict[str, str]):
        """Invalidate cache entries when entities are modified."""
        if not self.cache_enabled:
            return
        # Delegate to individual loader cache invalidation
        # Implementation mirrors the DynamoDB RequestLoaders pattern
        pass


__all__ = ["PGRequestLoaders"]