# -*- coding: utf-8 -*-
"""DynamoDB model package — PynamoDB models, cache, utils, and batch loaders."""
from __future__ import print_function

__author__ = "silvaengine"

# Lazy imports — models are imported on demand to avoid pulling in
# heavy dependencies (neo4j, silvaengine_dynamodb_base) at package
# import time.  This keeps unrelated code paths from failing when
# optional pieces are not installed.


def __getattr__(name):
    _model_map = {
        "Neo4jInstanceModel": ".neo4j_instance",
        "DocumentModel": ".document",
        "GraphSchemaModel": ".graph_schema",
        "RequestModel": ".request",
        "DocumentProcessErrorModel": ".document_process_error",
    }
    if name in _model_map:
        import importlib

        module = importlib.import_module(_model_map[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Neo4jInstanceModel",
    "DocumentModel",
    "GraphSchemaModel",
    "RequestModel",
    "DocumentProcessErrorModel",
]