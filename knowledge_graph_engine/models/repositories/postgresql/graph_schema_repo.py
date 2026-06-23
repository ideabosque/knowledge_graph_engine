# -*- coding: utf-8 -*-
"""PostgreSQL repository for GraphSchema entity.

Implements the single-active invariant using a transaction:
deactivate all other active schemas before activating a new one.
The partial unique index on the table provides database-level enforcement.
"""
from __future__ import print_function

__author__ = "silvaengine"

import traceback
from typing import Any, Dict, Optional

import pendulum

from ....handlers.config import Config
from ....types.graph_schema import GraphSchemaListType, GraphSchemaType

from ...postgresql.base import normalize_row
from ...postgresql.graph_schema import GraphSchemaModel
from ..base import EntityRepository


class GraphSchemaPGRepository(EntityRepository):
    """PostgreSQL repository for GraphSchema entity."""

    @property
    def entity_type(self) -> str:
        return "graph_schema"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        schema_name = keys.get("schema_name")
        if not partition_key or not schema_name:
            return None
        session = Config.db_session
        row = (
            session.query(GraphSchemaModel)
            .filter(
                GraphSchemaModel.partition_key == partition_key,
                GraphSchemaModel.schema_name == schema_name,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        schema_name = keys.get("schema_name")
        if not partition_key or not schema_name:
            return 0
        session = Config.db_session
        return (
            session.query(GraphSchemaModel)
            .filter(
                GraphSchemaModel.partition_key == partition_key,
                GraphSchemaModel.schema_name == schema_name,
            )
            .count()
        )

    def list(self, info: Any, **filters: Any) -> Any:
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        schema_type = filters.get("schema_type")
        statuses = filters.get("statuses")
        updated_at_gt = filters.get("updated_at_gt")
        updated_at_lt = filters.get("updated_at_lt")

        query = session.query(GraphSchemaModel)
        if partition_key:
            query = query.filter(GraphSchemaModel.partition_key == partition_key)
        if schema_type:
            query = query.filter(GraphSchemaModel.schema_type == schema_type)
        if statuses:
            query = query.filter(GraphSchemaModel.status.in_(statuses))
        if updated_at_gt:
            query = query.filter(GraphSchemaModel.updated_at > updated_at_gt)
        if updated_at_lt:
            query = query.filter(GraphSchemaModel.updated_at < updated_at_lt)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(GraphSchemaModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        schema_list = [self.get_type(info, row) for row in rows]
        return GraphSchemaListType(graph_schema_list=schema_list, total=total)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        schema_name = kwargs.get("schema_name")

        try:
            row = (
                session.query(GraphSchemaModel)
                .filter(
                    GraphSchemaModel.partition_key == partition_key,
                    GraphSchemaModel.schema_name == schema_name,
                )
                .first()
            )

            new_status = kwargs.get("status", "active")

            if not row:
                # New insert: if activating, deactivate others first
                if new_status == "active":
                    self._deactivate_active_schemas(session, partition_key)

                row = self._create_row(info, **kwargs)
                session.add(row)
            else:
                # Update: if activating, deactivate others (excluding this one)
                if new_status == "active" and row.status != "active":
                    self._deactivate_active_schemas(session, partition_key, exclude=schema_name)

                field_map = [
                    "schema_type", "schema_definition", "source_text_hash",
                    "neo4j_schema_string", "text2cypher_examples", "status", "updated_by",
                ]
                for field in field_map:
                    if field in kwargs:
                        val = kwargs[field]
                        setattr(row, field, None if val == "null" else val)
                row.updated_at = pendulum.now("UTC")

            session.commit()
            session.refresh(row)
            return normalize_row(row)
        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def _create_row(self, info: Any, **kwargs: Any) -> GraphSchemaModel:
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        endpoint_id = info.context.get("endpoint_id")
        part_id = info.context.get("part_id")

        cols = {
            "partition_key": partition_key,
            "schema_name": kwargs["schema_name"],
            "endpoint_id": endpoint_id,
            "part_id": part_id,
            "schema_type": kwargs.get("schema_type", "auto"),
            "schema_definition": kwargs.get("schema_definition", {}),
            "updated_by": kwargs.get("updated_by"),
            "created_at": kwargs.get("created_at", pendulum.now("UTC")),
            "updated_at": kwargs.get("updated_at", pendulum.now("UTC")),
        }
        for key in ["source_text_hash", "neo4j_schema_string", "text2cypher_examples", "status"]:
            if key in kwargs:
                cols[key] = kwargs[key]

        return GraphSchemaModel(**cols)

    def _deactivate_active_schemas(
        self, session: Any, partition_key: str, exclude: str = None
    ) -> None:
        """Deactivate all active schemas for a partition, optionally excluding one."""
        query = session.query(GraphSchemaModel).filter(
            GraphSchemaModel.partition_key == partition_key,
            GraphSchemaModel.status == "active",
        )
        if exclude:
            query = query.filter(GraphSchemaModel.schema_name != exclude)
        for schema in query.all():
            schema.status = "inactive"
            schema.updated_at = pendulum.now("UTC")

    def delete(self, info: Any, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        schema_name = kwargs.get("schema_name")

        try:
            row = (
                session.query(GraphSchemaModel)
                .filter(
                    GraphSchemaModel.partition_key == partition_key,
                    GraphSchemaModel.schema_name == schema_name,
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

    def get_type(self, info: Any, row: Any) -> Optional[GraphSchemaType]:
        data = normalize_row(row)
        if data is None:
            return None
        if data.get("schema_definition") is None:
            data["schema_definition"] = {}
        return GraphSchemaType(**data)

    def resolve_single(self, info: Any, **kwargs: Any) -> Optional[GraphSchemaType]:
        partition_key = info.context.get("partition_key")
        schema_name = kwargs.get("schema_name")
        if not partition_key or not schema_name:
            return None
        data = self.get(partition_key=partition_key, schema_name=schema_name)
        if data is None:
            return None
        if data.get("schema_definition") is None:
            data["schema_definition"] = {}
        return GraphSchemaType(**data)

    def resolve_active(self, partition_key: str) -> Optional[Dict[str, Any]]:
        """Get the active graph schema for a partition."""
        session = Config.db_session
        row = (
            session.query(GraphSchemaModel)
            .filter(
                GraphSchemaModel.partition_key == partition_key,
                GraphSchemaModel.status == "active",
            )
            .order_by(GraphSchemaModel.updated_at.desc())
            .first()
        )
        return normalize_row(row) if row else None


__all__ = ["GraphSchemaPGRepository"]