# -*- coding: utf-8 -*-
"""DynamoDB repository for DocumentProcessError entity."""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from ..base import EntityRepository
from ._base import _normalize

from ...dynamodb import document_process_error as _dpe_mod


class DocumentProcessErrorRepository(EntityRepository):
    """DynamoDB repository for DocumentProcessError entity."""

    @property
    def entity_type(self) -> str:
        return "document_process_error"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        process_error_uuid = keys.get("process_error_uuid")
        if not partition_key or not process_error_uuid:
            return None
        count = _dpe_mod.get_document_process_error_count(
            partition_key, process_error_uuid
        )
        if count == 0:
            return None
        return _normalize(
            _dpe_mod.get_document_process_error(partition_key, process_error_uuid)
        )

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        process_error_uuid = keys.get("process_error_uuid")
        if not partition_key or not process_error_uuid:
            return 0
        return _dpe_mod.get_document_process_error_count(
            partition_key, process_error_uuid
        )

    def list(self, info: Any, **filters: Any) -> Any:
        # DocumentProcessError has no list resolver in the current code.
        # Return empty list type shape if needed.
        raise NotImplementedError(
            "list is not implemented for document_process_error"
        )

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return _dpe_mod.insert_update_document_process_error(info, **kwargs)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        return _dpe_mod.delete_document_process_error(info, **kwargs)

    def get_type(self, info: Any, error: Any) -> Any:
        return _dpe_mod.get_document_process_error_type(info, error)