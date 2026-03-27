# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from .base import SafeDataLoader
from .document_loader import DocumentLoader
from .graph_schema_loader import GraphSchemaLoader


class RequestLoaders:
    """Container for all batch loaders in a single request."""

    def __init__(self):
        self.document_loader = DocumentLoader()
        self.graph_schema_loader = GraphSchemaLoader()


def get_loaders(context):
    """Get or create request loaders from context."""
    if "loaders" not in context:
        context["loaders"] = RequestLoaders()
    return context["loaders"]