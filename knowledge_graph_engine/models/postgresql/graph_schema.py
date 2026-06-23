# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for GraphSchema entity.

Mirrors the DynamoDB GraphSchemaModel schema. Enforces the single-active
invariant via a partial unique index on (partition_key) WHERE status = 'active'.
"""
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


class GraphSchemaModel(Base):
    """SQLAlchemy model for the GraphSchema entity (table: graph_schemas)."""

    @declared_attr
    def __tablename__(cls) -> str:
        return prefixed_table("graph_schemas")

    # Primary key: composite (partition_key, schema_name)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    schema_name = Column(String(255), nullable=False, primary_key=True)

    # Tenant metadata
    endpoint_id = Column(String(64))
    part_id = Column(String(64))

    # Schema attributes
    schema_type = Column(String(64), default="auto")
    schema_definition = Column(JSONB)
    source_text_hash = Column(String(128))
    neo4j_schema_string = Column(Text)
    text2cypher_examples = Column(JSONB)

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
        Index(prefixed_index("idx_graph_schemas_partition_updated_at"), "partition_key", "updated_at"),
        Index(prefixed_index("idx_graph_schemas_partition_status"), "partition_key", "status"),
        # Partial unique index for single-active invariant
        Index(
            prefixed_index("idx_graph_schemas_one_active"),
            "partition_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )


__all__ = ["GraphSchemaModel"]