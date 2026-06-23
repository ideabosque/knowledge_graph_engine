# -*- coding: utf-8 -*-
"""PostgreSQL repository for Request entity."""
from __future__ import print_function

__author__ = "silvaengine"

import traceback
import uuid as _uuid
from typing import Any, Dict, Optional

import pendulum

from ....handlers.config import Config
from ....types.request import RequestListType, RequestType

from ...postgresql.base import normalize_row
from ...postgresql.request import RequestModel
from ..base import EntityRepository


class RequestPGRepository(EntityRepository):
    """PostgreSQL repository for Request entity."""

    @property
    def entity_type(self) -> str:
        return "request"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        partition_key = keys.get("partition_key")
        request_uuid = keys.get("request_uuid")
        if not partition_key or not request_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(RequestModel)
            .filter(
                RequestModel.partition_key == partition_key,
                RequestModel.request_uuid == request_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        partition_key = keys.get("partition_key")
        request_uuid = keys.get("request_uuid")
        if not partition_key or not request_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(RequestModel)
            .filter(
                RequestModel.partition_key == partition_key,
                RequestModel.request_uuid == request_uuid,
            )
            .count()
        )

    def list(self, info: Any, **filters: Any) -> Any:
        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        search_mode = filters.get("search_mode")

        query = session.query(RequestModel)
        if partition_key:
            query = query.filter(RequestModel.partition_key == partition_key)
        if search_mode is not None:
            query = query.filter(RequestModel.search_mode == search_mode)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(RequestModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        request_list = [self.get_type(info, row) for row in rows]
        return RequestListType(request_list=request_list, total=total)

    def insert_update(self, info: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        request_uuid = kwargs.get("request_uuid")

        try:
            if request_uuid:
                row = (
                    session.query(RequestModel)
                    .filter(
                        RequestModel.partition_key == partition_key,
                        RequestModel.request_uuid == request_uuid,
                    )
                    .first()
                )
                if not row:
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "user_query", "cypher_query", "search_mode",
                        "results", "updated_by",
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

    def _create_row(self, info: Any, **kwargs: Any) -> RequestModel:
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        endpoint_id = info.context.get("endpoint_id")
        part_id = info.context.get("part_id")

        request_uuid = kwargs.get("request_uuid")
        if not request_uuid:
            request_uuid = f"req-{pendulum.now('UTC').int_timestamp}-{_uuid.uuid4().hex[:8]}"

        cols = {
            "partition_key": partition_key,
            "request_uuid": request_uuid,
            "endpoint_id": endpoint_id,
            "part_id": part_id,
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in ["user_query", "cypher_query", "search_mode", "results", "updated_by"]:
            if key in kwargs:
                cols[key] = kwargs[key]

        return RequestModel(**cols)

    def delete(self, info: Any, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        partition_key = info.context.get("partition_key") or kwargs.get("partition_key")
        request_uuid = kwargs.get("request_uuid")

        try:
            row = (
                session.query(RequestModel)
                .filter(
                    RequestModel.partition_key == partition_key,
                    RequestModel.request_uuid == request_uuid,
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

    def get_type(self, info: Any, row: Any) -> Optional[RequestType]:
        data = normalize_row(row)
        if data is None:
            return None
        return RequestType(**data)

    def resolve_single(self, info: Any, **kwargs: Any) -> Optional[RequestType]:
        partition_key = info.context.get("partition_key")
        request_uuid = kwargs.get("request_uuid")
        if not partition_key or not request_uuid:
            return None
        data = self.get(partition_key=partition_key, request_uuid=request_uuid)
        if data is None:
            return None
        return RequestType(**data)


__all__ = ["RequestPGRepository"]