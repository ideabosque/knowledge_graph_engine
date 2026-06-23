# -*- coding: utf-8 -*-
"""PostgreSQL repository for Document entity."""
from __future__ import print_function

__author__ = "silvaengine"

import traceback
from typing import Any, Dict, Optional

import pendulum

from ....handlers.config import Config
from ....types.document import DocumentListType, DocumentType

from ...postgresql.base import normalize_row
from ...postgresql.document import DocumentModel
from ..base import EntityRepository


class DocumentPGRepository(EntityRepository):
    """PostgreSQL repository for Document entity."""

    @property
    def entity_type(self) -> str:
        return "document"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        document_uuid = keys.get("document_uuid")
        if not partition_key or not document_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(DocumentModel)
            .filter(
                DocumentModel.partition_key == partition_key,
                DocumentModel.document_uuid == document_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        document_uuid = keys.get("document_uuid")
        if not partition_key or not document_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(DocumentModel)
            .filter(
                DocumentModel.partition_key == partition_key,
                DocumentModel.document_uuid == document_uuid,
            )
            .count()
        )

    def list(self, info: Any, **filters: Any) -> Any:
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        document_source = filters.get("document_source")
        document_external_id = filters.get("document_external_id")
        statuses = filters.get("statuses")
        updated_at_gt = filters.get("updated_at_gt")
        updated_at_lt = filters.get("updated_at_lt")

        query = session.query(DocumentModel)
        if partition_key:
            query = query.filter(DocumentModel.partition_key == partition_key)
        if document_source:
            query = query.filter(DocumentModel.document_source == document_source)
        if document_external_id:
            query = query.filter(DocumentModel.document_external_id == document_external_id)
        if statuses:
            query = query.filter(DocumentModel.status.in_(statuses))
        if updated_at_gt:
            query = query.filter(DocumentModel.updated_at > updated_at_gt)
        if updated_at_lt:
            query = query.filter(DocumentModel.updated_at < updated_at_lt)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(DocumentModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        document_list = [self.get_type(info, row) for row in rows]
        return DocumentListType(document_list=document_list, total=total)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        document_uuid = kwargs.get("document_uuid")

        try:
            if document_uuid:
                row = (
                    session.query(DocumentModel)
                    .filter(
                        DocumentModel.partition_key == partition_key,
                        DocumentModel.document_uuid == document_uuid,
                    )
                    .first()
                )
                if not row:
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "document_source", "document_external_id", "chunk_index",
                        "document_title", "content", "content_embedding",
                        "status", "updated_by",
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

    def _create_row(self, info: Any, **kwargs: Any) -> DocumentModel:
        import uuid as _uuid

        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        endpoint_id = info.context.get("endpoint_id")
        part_id = info.context.get("part_id")

        cols = {
            "partition_key": partition_key,
            "endpoint_id": endpoint_id,
            "part_id": part_id,
            "document_source": kwargs.get("document_source", "unknown"),
            "updated_by": kwargs.get("updated_by"),
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        document_uuid = kwargs.get("document_uuid")
        if not document_uuid:
            document_uuid = f"doc-{pendulum.now('UTC').int_timestamp}-{str(_uuid.uuid4())[:8]}"
        cols["document_uuid"] = document_uuid

        for key in [
            "document_external_id", "chunk_index", "document_title",
            "content", "content_embedding", "status",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        return DocumentModel(**cols)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        document_uuid = kwargs.get("document_uuid")

        try:
            row = (
                session.query(DocumentModel)
                .filter(
                    DocumentModel.partition_key == partition_key,
                    DocumentModel.document_uuid == document_uuid,
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

    def get_type(self, info: Any, row: Any) -> Optional[DocumentType]:
        data = normalize_row(row)
        if data is None:
            return None
        return DocumentType(**data)

    def resolve_single(self, info: Any, **kwargs: Any) -> Optional[DocumentType]:
        partition_key = info.context.get("partition_key")
        document_uuid = kwargs.get("document_uuid")
        if not partition_key or not document_uuid:
            return None
        data = self.get(partition_key=partition_key, document_uuid=document_uuid)
        if data is None:
            return None
        return DocumentType(**data)


__all__ = ["DocumentPGRepository"]