# -*- coding: utf-8 -*-
"""DynamoDB repository for Document entity."""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from ..base import EntityRepository
from ._base import _normalize

from ...dynamodb import document as _document_mod


class DocumentRepository(EntityRepository):
    """DynamoDB repository for Document entity."""

    @property
    def entity_type(self) -> str:
        return "document"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        document_uuid = keys.get("document_uuid")
        if not partition_key or not document_uuid:
            return None
        count = _document_mod.get_document_count(partition_key, document_uuid)
        if count == 0:
            return None
        return _normalize(_document_mod.get_document(partition_key, document_uuid))

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        document_uuid = keys.get("document_uuid")
        if not partition_key or not document_uuid:
            return 0
        return _document_mod.get_document_count(partition_key, document_uuid)

    def list(self, info: Any, **filters: Any) -> Any:
        return _document_mod.resolve_document_list(info, **filters)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _document_mod.insert_update_document(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _document_mod.delete_document(info, **kwargs)

    def get_type(self, info: Any, document: Any) -> Any:
        return _document_mod.get_document_type(info, document)

    def resolve_single(self, info: Any, **kwargs: Any) -> Any:
        return _document_mod.resolve_document(info, **kwargs)