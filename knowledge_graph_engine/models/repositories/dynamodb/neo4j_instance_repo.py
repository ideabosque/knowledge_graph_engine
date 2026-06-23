# -*- coding: utf-8 -*-
"""DynamoDB repository for Neo4jInstance entity."""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from ..base import EntityRepository
from ._base import _normalize

from ...dynamodb import neo4j_instance as _neo4j_instance_mod


class Neo4jInstanceRepository(EntityRepository):
    """DynamoDB repository for Neo4jInstance entity."""

    @property
    def entity_type(self) -> str:
        return "neo4j_instance"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        instance_id = keys.get("instance_id")
        if not partition_key or not instance_id:
            return None
        count = _neo4j_instance_mod.get_neo4j_instance_count(partition_key, instance_id)
        if count == 0:
            return None
        return _normalize(
            _neo4j_instance_mod.get_neo4j_instance(partition_key, instance_id)
        )

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        instance_id = keys.get("instance_id")
        if not partition_key or not instance_id:
            return 0
        return _neo4j_instance_mod.get_neo4j_instance_count(partition_key, instance_id)

    def list(self, info: Any, **filters: Any) -> Any:
        return _neo4j_instance_mod.resolve_neo4j_instance_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _neo4j_instance_mod.insert_update_neo4j_instance(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _neo4j_instance_mod.delete_neo4j_instance(info, **kwargs)

    def get_type(self, info: Any, instance: Any) -> Any:
        return _neo4j_instance_mod.get_neo4j_instance_type(info, instance)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        partition_key = info.context.get("partition_key")
        instance_id = kwargs.get("instance_id")
        if not partition_key or not instance_id:
            return None
        try:
            instance = _neo4j_instance_mod.get_neo4j_instance(
                partition_key, instance_id
            )
            return _neo4j_instance_mod.get_neo4j_instance_type(info, instance)
        except Exception:
            return None

    # KGE-specific helpers

    def resolve_active(self, partition_key: str) -> Optional[Dict[str, Any]]:
        """Get the active Neo4j instance for a partition."""
        return _normalize(_neo4j_instance_mod.get_active_neo4j_instance(partition_key))