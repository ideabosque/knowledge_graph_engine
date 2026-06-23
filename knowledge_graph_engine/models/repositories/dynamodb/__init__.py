# -*- coding: utf-8 -*-
"""DynamoDB repositories — thin wrappers over existing PynamoDB model functions.

Each entity has its own repo file. The register_all function instantiates
all 5 repositories and registers them with the dispatch registry.
"""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Dict

from ..base import EntityRepository


def register_all(registry: Dict[str, EntityRepository]) -> None:
    """Register all DynamoDB repositories into the given registry dict."""
    from .document_repo import DocumentRepository
    from .graph_schema_repo import GraphSchemaRepository
    from .neo4j_instance_repo import Neo4jInstanceRepository
    from .request_repo import RequestRepository
    from .document_process_error_repo import DocumentProcessErrorRepository

    repos = [
        DocumentRepository(),
        GraphSchemaRepository(),
        Neo4jInstanceRepository(),
        RequestRepository(),
        DocumentProcessErrorRepository(),
    ]
    for repo in repos:
        registry[repo.entity_type] = repo


__all__ = ["register_all"]