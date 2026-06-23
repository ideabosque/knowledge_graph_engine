# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy model for Neo4jInstance entity.

Enforces the single-active invariant via a partial unique index on
(partition_key) WHERE status = 'active'.
"""
from __future__ import print_function

__author__ = "silvaengine"

from sqlalchemy import (
    Column,
    Index,
    Integer,
    String,
    TIMESTAMP,
    text,
)
from sqlalchemy.orm import declared_attr

from .base import Base, prefixed_index, prefixed_table


class Neo4jInstanceModel(Base):
    """SQLAlchemy model for the Neo4jInstance entity (table: neo4j_instances)."""

    @declared_attr
    def __tablename__(cls) -> str:
        return prefixed_table("neo4j_instances")

    # Primary key: composite (partition_key, instance_id)
    partition_key = Column(String(128), nullable=False, primary_key=True)
    instance_id = Column(String(128), nullable=False, primary_key=True)

    # Tenant metadata
    endpoint_id = Column(String(64))
    part_id = Column(String(64))

    # Neo4j connection attributes
    neo4j_uri = Column(String(512), nullable=False)
    neo4j_username = Column(String(128), default="neo4j")
    neo4j_password = Column(String(256), nullable=False)
    neo4j_database = Column(String(128), default="neo4j")
    container_id = Column(String(128))

    # Status & pool config
    status = Column(String(32), default="active")
    max_connection_pool_size = Column(Integer, default=5)

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
        Index(prefixed_index("idx_neo4j_instances_partition_status"), "partition_key", "status"),
        # Partial unique index for single-active invariant
        Index(
            prefixed_index("idx_neo4j_instances_one_active"),
            "partition_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )


__all__ = ["Neo4jInstanceModel"]