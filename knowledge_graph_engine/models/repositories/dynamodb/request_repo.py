# -*- coding: utf-8 -*-
"""DynamoDB repository for Request entity."""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from ..base import EntityRepository
from ._base import _normalize

from ...dynamodb import request as _request_mod


class RequestRepository(EntityRepository):
    """DynamoDB repository for Request entity."""

    @property
    def entity_type(self) -> str:
        return "request"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        request_uuid = keys.get("request_uuid")
        if not partition_key or not request_uuid:
            return None
        count = _request_mod.get_request_count(partition_key, request_uuid)
        if count == 0:
            return None
        return _normalize(_request_mod.get_request(partition_key, request_uuid))

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        request_uuid = keys.get("request_uuid")
        if not partition_key or not request_uuid:
            return 0
        return _request_mod.get_request_count(partition_key, request_uuid)

    def list(self, info: Any, **filters: Any) -> Any:
        return _request_mod.resolve_request_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _request_mod.insert_update_request(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _request_mod.delete_request(info, **kwargs)

    def get_type(self, info: Any, request: Any) -> Any:
        return _request_mod.get_request_type(info, request)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _request_mod.resolve_request(info, **kwargs)