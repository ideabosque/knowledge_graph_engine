# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from promise import Promise

from ..graph_schema import GraphSchemaModel
from .base import SafeDataLoader


class GraphSchemaLoader(SafeDataLoader):
    """Loads graph schemas by (partition_key, schema_name) tuples."""

    def batch_load_fn(self, keys):
        results = []
        for partition_key, schema_name in keys:
            try:
                schema = GraphSchemaModel.get(partition_key, schema_name)
                from ...utils.normalization import normalize_to_json
                results.append(normalize_to_json(schema))
            except GraphSchemaModel.DoesNotExist:
                results.append(None)
        return Promise.resolve(results)