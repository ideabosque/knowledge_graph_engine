# -*- coding: utf-8 -*-
"""PostgreSQL repositories for the PostgreSQL backend.

All PG repository files live under models/repositories/postgresql/.
Import paths:
  from ...postgresql.base import normalize_row       # models/postgresql/base.py
  from ...postgresql.document import DocumentModel    # models/postgresql/document.py
  from ..base import EntityRepository                 # models/repositories/base.py
  from ....handlers.config import Config              # knowledge_graph_engine/handlers/config.py
"""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Dict

from ..base import EntityRepository


def register_all(registry: Dict[str, EntityRepository]) -> None:
    """Register all PostgreSQL repositories into the given registry dict."""
    _repos = [
        ("document_repo", "DocumentPGRepository"),
        ("graph_schema_repo", "GraphSchemaPGRepository"),
        ("neo4j_instance_repo", "Neo4jInstancePGRepository"),
        ("request_repo", "RequestPGRepository"),
        ("document_process_error_repo", "DocumentProcessErrorPGRepository"),
    ]
    for module_name, class_name in _repos:
        try:
            import importlib

            mod = importlib.import_module(f".{module_name}", package=__name__)
            repo_cls = getattr(mod, class_name)
            repo = repo_cls()
            registry[repo.entity_type] = repo
        except ImportError:
            pass


__all__ = ["register_all"]