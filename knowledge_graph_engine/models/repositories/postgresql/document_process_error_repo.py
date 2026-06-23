# -*- coding: utf-8 -*-
"""PostgreSQL repository for DocumentProcessError entity."""
from __future__ import print_function

__author__ = "silvaengine"

import traceback
import uuid as _uuid
from typing import Any, Dict, Optional

import pendulum

from ....handlers.config import Config
from ....types.document_process_error import DocumentProcessErrorType

from ...postgresql.base import normalize_row
from ...postgresql.document_process_error import DocumentProcessErrorModel
from ..base import EntityRepository


class DocumentProcessErrorPGRepository(EntityRepository):
    """PostgreSQL repository for DocumentProcessError entity."""

    @property
    def entity_type(self) -> str:
        return "document_process_error"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        process_error_uuid = keys.get("process_error_uuid")
        if not partition_key or not process_error_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(DocumentProcessErrorModel)
            .filter(
                DocumentProcessErrorModel.partition_key == partition_key,
                DocumentProcessErrorModel.process_error_uuid == process_error_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        process_error_uuid = keys.get("process_error_uuid")
        if not partition_key or not process_error_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(DocumentProcessErrorModel)
            .filter(
                DocumentProcessErrorModel.partition_key == partition_key,
                DocumentProcessErrorModel.process_error_uuid == process_error_uuid,
            )
            .count()
        )

    def list(self, info: Any, **filters: Any) -> Any:
        raise NotImplementedError(
            "list is not implemented for document_process_error"
        )

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        process_error_uuid = kwargs.get("process_error_uuid")

        try:
            if process_error_uuid:
                row = (
                    session.query(DocumentProcessErrorModel)
                    .filter(
                        DocumentProcessErrorModel.partition_key == partition_key,
                        DocumentProcessErrorModel.process_error_uuid == process_error_uuid,
                    )
                    .first()
                )
                if not row:
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "document_source", "document_external_id", "chunk_index",
                        "error_message", "process_status", "process_count",
                    ]
                    for field in field_map:
                        if field in kwargs:
                            val = kwargs[field]
                            setattr(row, field, None if val == "null" else val)
                    row.updated_at = pendulum.now("UTC")
            else:
                row = self._create_row(info, **kwargs)
                session.add(row)

            session.commit()
            session.refresh(row)
            return normalize_row(row)
        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def _create_row(self, info: Any, **kwargs: Any) -> DocumentProcessErrorModel:
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")

        process_error_uuid = kwargs.get("process_error_uuid")
        if not process_error_uuid:
            process_error_uuid = f"err-{pendulum.now('UTC').int_timestamp}-{str(_uuid.uuid4())[:8]}"

        cols = {
            "partition_key": partition_key,
            "process_error_uuid": process_error_uuid,
            "document_source": kwargs.get("document_source", "unknown"),
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "document_external_id", "chunk_index", "error_message",
            "process_status", "process_count",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        return DocumentProcessErrorModel(**cols)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        process_error_uuid = kwargs.get("process_error_uuid")

        try:
            row = (
                session.query(DocumentProcessErrorModel)
                .filter(
                    DocumentProcessErrorModel.partition_key == partition_key,
                    DocumentProcessErrorModel.process_error_uuid == process_error_uuid,
                )
                .first()
            )
            if not row:
                return True
            session.delete(row)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def get_type(self, info: Any, row: Any) -> Optional[DocumentProcessErrorType]:
        data = normalize_row(row)
        if data is None:
            return None
        return DocumentProcessErrorType(**data)


__all__ = ["DocumentProcessErrorPGRepository"]