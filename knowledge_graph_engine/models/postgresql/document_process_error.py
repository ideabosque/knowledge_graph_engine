# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for DocumentProcessError entity."""
from __future__ import print_function

__author__ = "silvaengine"

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    TIMESTAMP,
    text,
)
from sqlalchemy.orm import declared_attr

from .base import Base, prefixed_table


class DocumentProcessErrorModel(Base):
    """SQLAlchemy model for the DocumentProcessError entity (table: document_process_errors)."""

    @declared_attr
    def __tablename__(cls) -> str:
        return prefixed_table("document_process_errors")

    # Primary key: composite (partition_key, process_error_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    process_error_uuid = Column(String(128), nullable=False, primary_key=True)

    # Error attributes
    document_source = Column(String(255), nullable=False)
    document_external_id = Column(String(255))
    chunk_index = Column(Integer)
    error_message = Column(Text)
    process_status = Column(String(32), default="failed")
    process_count = Column(Integer, default=0)

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


__all__ = ["DocumentProcessErrorModel"]