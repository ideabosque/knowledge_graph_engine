# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, List, Tuple

from promise import Promise

from ..graph_schema import GraphSchemaModel
from .base import SafeDataLoader, normalize_model, Key


class GraphSchemaLoader(SafeDataLoader):
    """Loads graph schemas by (partition_key, schema_name) tuples."""

    def __init__(self, logger=None, cache_enabled=True, **kwargs):
        super(GraphSchemaLoader, self).__init__(
            logger=logger, cache_enabled=cache_enabled, **kwargs
        )

    def batch_load_fn(self, keys: List[Key]) -> Promise:
        results = []
        for partition_key, schema_name in keys:
            try:
                schema = GraphSchemaModel.get(partition_key, schema_name)
                results.append(normalize_model(schema))
            except GraphSchemaModel.DoesNotExist:
                results.append(None)
        return Promise.resolve(results)