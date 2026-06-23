# -*- coding: utf-8 -*-
"""DynamoDB repository for GraphSchema entity."""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from ..base import EntityRepository
from ._base import _normalize

from ...dynamodb import graph_schema as _graph_schema_mod


class GraphSchemaRepository(EntityRepository):
    """DynamoDB repository for GraphSchema entity."""

    @property
    def entity_type(self) -> str:
        return "graph_schema"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        schema_name = keys.get("schema_name")
        if not partition_key or not schema_name:
            return None
        count = _graph_schema_mod.get_graph_schema_count(partition_key, schema_name)
        if count == 0:
            return None
        return _normalize(_graph_schema_mod.get_graph_schema(partition_key, schema_name))

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        schema_name = keys.get("schema_name")
        if not partition_key or not schema_name:
            return 0
        return _graph_schema_mod.get_graph_schema_count(partition_key, schema_name)

    def list(self, info: Any, **filters: Any) -> Any:
        return _graph_schema_mod.resolve_graph_schema_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _graph_schema_mod.insert_update_graph_schema(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _graph_schema_mod.delete_graph_schema(info, **kwargs)

    def get_type(self, info: Any, schema: Any) -> Any:
        return _graph_schema_mod.get_graph_schema_type(info, schema)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _graph_schema_mod.resolve_graph_schema(info, **kwargs)

    # KGE-specific helpers

    def resolve_active(self, partition_key: str) -> Optional[Dict[str, Any]]:
        """Get the active graph schema for a partition."""
        return _normalize(_graph_schema_mod.get_active_graph_schema(partition_key))

    def get_schemas_for_partition(self, partition_key: str) -> list:
        """Get all schemas for a partition."""
        return [
            _normalize(s)
            for s in _graph_schema_mod.get_graph_schemas_for_partition(partition_key)
        ]