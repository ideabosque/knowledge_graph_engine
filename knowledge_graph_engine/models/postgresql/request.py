# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for Request entity."""
from __future__ import print_function

__author__ = "silvaengine"

from sqlalchemy import (
    Column,
    Index,
    String,
    Text,
    TIMESTAMP,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr

from .base import Base, prefixed_index, prefixed_table


class RequestModel(Base):
    """SQLAlchemy model for the Request entity (table: requests)."""

    @declared_attr
    def __tablename__(cls) -> str:
        return prefixed_table("requests")

    # Primary key: composite (partition_key, request_uuid)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    request_uuid = Column(String(128), nullable=False, primary_key=True)

    # Tenant metadata
    endpoint_id = Column(String(64))
    part_id = Column(String(64))

    # Request attributes
    user_query = Column(Text)
    cypher_query = Column(Text)
    search_mode = Column(String(64), default="text2cypher")
    results = Column(JSONB)

    # Audit
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
        Index(prefixed_index("idx_requests_partition_search_mode"), "partition_key", "search_mode"),
    )


__all__ = ["RequestModel"]