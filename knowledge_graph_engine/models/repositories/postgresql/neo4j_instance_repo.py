# -*- coding: utf-8 -*-
"""PostgreSQL repository for Neo4jInstance entity.

Implements the single-active invariant and driver-cache invalidation
on writes/deletes, matching the DynamoDB behavior.
"""
from __future__ import print_function

__author__ = "silvaengine"

import traceback
from typing import Any, Dict, Optional

import pendulum

from ....handlers.config import Config
from ....types.neo4j_instance import Neo4jInstanceListType, Neo4jInstanceType

from ...postgresql.base import normalize_row
from ...postgresql.neo4j_instance import Neo4jInstanceModel
from ..base import EntityRepository


class Neo4jInstancePGRepository(EntityRepository):
    """PostgreSQL repository for Neo4jInstance entity."""

    @property
    def entity_type(self) -> str:
        return "neo4j_instance"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        instance_id = keys.get("instance_id")
        if not partition_key or not instance_id:
            return None
        session = Config.db_session
        row = (
            session.query(Neo4jInstanceModel)
            .filter(
                Neo4jInstanceModel.partition_key == partition_key,
                Neo4jInstanceModel.instance_id == instance_id,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        instance_id = keys.get("instance_id")
        if not partition_key or not instance_id:
            return 0
        session = Config.db_session
        return (
            session.query(Neo4jInstanceModel)
            .filter(
                Neo4jInstanceModel.partition_key == partition_key,
                Neo4jInstanceModel.instance_id == instance_id,
            )
            .count()
        )

    def list(self, info: Any, **filters: Any) -> Any:
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        statuses = filters.get("statuses")

        query = session.query(Neo4jInstanceModel)
        if partition_key:
            query = query.filter(Neo4jInstanceModel.partition_key == partition_key)
        if statuses:
            query = query.filter(Neo4jInstanceModel.status.in_(statuses))

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(Neo4jInstanceModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        instance_list = [self.get_type(info, row) for row in rows]
        return Neo4jInstanceListType(neo4j_instance_list=instance_list, total=total)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        instance_id = kwargs.get("instance_id", "default")

        try:
            row = (
                session.query(Neo4jInstanceModel)
                .filter(
                    Neo4jInstanceModel.partition_key == partition_key,
                    Neo4jInstanceModel.instance_id == instance_id,
                )
                .first()
            )

            new_status = kwargs.get("status", "active")

            if not row:
                if new_status == "active":
                    self._deactivate_active_instances(session, partition_key)
                row = self._create_row(info, **kwargs)
                session.add(row)
            else:
                if new_status == "active" and row.status != "active":
                    self._deactivate_active_instances(session, partition_key, exclude=instance_id)

                field_map = [
                    "neo4j_uri", "neo4j_username", "neo4j_password",
                    "neo4j_database", "container_id", "status",
                    "max_connection_pool_size",
                ]
                for field in field_map:
                    if field in kwargs:
                        val = kwargs[field]
                        setattr(row, field, None if val == "null" else val)
                row.updated_at = pendulum.now("UTC")

            session.commit()
            session.refresh(row)

            # Driver-cache invalidation: close cached driver so new active is picked up
            if new_status == "active":
                from ....handlers.neo4j_connection_manager import Neo4jConnectionManager
                Neo4jConnectionManager.close_driver(partition_key)

            return normalize_row(row)
        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def _create_row(self, info: Any, **kwargs: Any) -> Neo4jInstanceModel:
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        endpoint_id = info.context.get("endpoint_id")
        part_id = info.context.get("part_id")
        instance_id = kwargs.get("instance_id", "default")

        cols = {
            "partition_key": partition_key,
            "instance_id": instance_id,
            "endpoint_id": endpoint_id,
            "part_id": part_id,
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "neo4j_uri", "neo4j_username", "neo4j_password",
            "neo4j_database", "container_id", "status", "max_connection_pool_size",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        return Neo4jInstanceModel(**cols)

    def _deactivate_active_instances(
        self, session: Any, partition_key: str, exclude: str = None
    ) -> None:
        """Deactivate all active instances for a partition, optionally excluding one."""
        query = session.query(Neo4jInstanceModel).filter(
            Neo4jInstanceModel.partition_key == partition_key,
            Neo4jInstanceModel.status == "active",
        )
        if exclude:
            query = query.filter(Neo4jInstanceModel.instance_id != exclude)
        for instance in query.all():
            instance.status = "inactive"
            instance.updated_at = pendulum.now("UTC")

    def delete(self, info: Any, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        instance_id = kwargs.get("instance_id")

        try:
            row = (
                session.query(Neo4jInstanceModel)
                .filter(
                    Neo4jInstanceModel.partition_key == partition_key,
                    Neo4jInstanceModel.instance_id == instance_id,
                )
                .first()
            )
            if not row:
                return True
            session.delete(row)
            session.commit()

            # Driver-cache invalidation on delete
            from ....handlers.neo4j_connection_manager import Neo4jConnectionManager
            Neo4jConnectionManager.close_driver(partition_key)
            Config.clear_graph_rag_util(partition_key)
            return True
        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def get_type(self, info: Any, row: Any) -> Optional[Neo4jInstanceType]:
        data = normalize_row(row)
        if data is None:
            return None
        return Neo4jInstanceType(**data)

    def resolve_single(self, info: Any, **kwargs: Any) -> Optional[Neo4jInstanceType]:
        partition_key = info.context.get("partition_key")
        instance_id = kwargs.get("instance_id")
        if not partition_key or not instance_id:
            return None
        data = self.get(partition_key=partition_key, instance_id=instance_id)
        if data is None:
            return None
        return Neo4jInstanceType(**data)

    def resolve_active(self, partition_key: str) -> Optional[Dict[str, Any]]:
        """Get the active Neo4j instance for a partition."""
        session = Config.db_session
        row = (
            session.query(Neo4jInstanceModel)
            .filter(
                Neo4jInstanceModel.partition_key == partition_key,
                Neo4jInstanceModel.status == "active",
            )
            .order_by(Neo4jInstanceModel.updated_at.desc())
            .first()
        )
        return normalize_row(row) if row else None


__all__ = ["Neo4jInstancePGRepository"]