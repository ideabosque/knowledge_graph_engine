# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for Document entity.

Mirrors the DynamoDB DocumentModel schema with PostgreSQL-appropriate types.
KGE uses string-based UUIDs (e.g. "doc-..."), not native UUID columns.
"""
from __future__ import print_function

__author__ = "silvaengine"

from sqlalchemy import (
    Column,
    Index,
    Integer,
    String,
    Text,
    TIMESTAMP,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr

from .base import Base, prefixed_index, prefixed_table


class DocumentModel(Base):
    """SQLAlchemy model for the Document entity (table: documents)."""

    @declared_attr
    def __tablename__(cls) -> str:
        return prefixed_table("documents")

    # Primary key: composite (partition_key, document_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    document_uuid = Column(String(128), nullable=False, primary_key=True)

    # Tenant metadata
    endpoint_id = Column(String(64))
    part_id = Column(String(64))

    # Document attributes
    document_source = Column(String(255), nullable=False)
    document_external_id = Column(String(255))
    chunk_index = Column(Integer, default=0)
    document_title = Column(String(512))
    content = Column(Text)
    content_embedding = Column(JSONB)

    # Status & audit
    status = Column(String(32), default="active")
    updated_by = Column(String(64))

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    __table_args__ = (
        Index(prefixed_index("idx_documents_partition_updated_at"), "partition_key", "updated_at"),
        Index(prefixed_index("idx_documents_partition_external_id"), "partition_key", "document_external_id"),
        Index(prefixed_index("idx_documents_partition_status"), "partition_key", "status"),
    )


__all__ = ["DocumentModel"]