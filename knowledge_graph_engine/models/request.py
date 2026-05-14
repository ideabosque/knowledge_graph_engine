# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import uuid
from typing import Any, Dict

import pendulum
from graphene import ResolveInfo
from pynamodb.attributes import ListAttribute, UnicodeAttribute, UTCDateTimeAttribute

from silvaengine_dynamodb_base import (
    BaseModel,
    delete_decorator,
    insert_update_decorator,
    resolve_list_decorator,
)
from silvaengine_utility import method_cache
from ..types.request import RequestListType, RequestType
from ..utils.normalization import normalize_to_json
from ..handlers.config import Config


class RequestModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "kge-requests"

    partition_key = UnicodeAttribute(hash_key=True)
    request_uuid = UnicodeAttribute(range_key=True)

    endpoint_id = UnicodeAttribute(null=True)
    part_id = UnicodeAttribute(null=True)

    user_query = UnicodeAttribute(null=True)
    cypher_query = UnicodeAttribute(null=True)
    search_mode = UnicodeAttribute(
        default="text2cypher"
    )  # vector, text2cypher, vector_cypher, hybrid
    results = ListAttribute(null=True)

    updated_by = UnicodeAttribute(null=True)
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("models", "request"),
    cache_enabled=Config.is_cache_enabled,
)
def get_request(partition_key: str, request_uuid: str) -> RequestModel:
    return RequestModel.get(partition_key, request_uuid)


def get_request_count(partition_key: str, request_uuid: str) -> int:
    return RequestModel.count(partition_key, RequestModel.request_uuid == request_uuid)


def get_request_type(info: ResolveInfo, request: RequestModel) -> RequestType:
    _ = info  # Keep for signature compatibility with decorators
    request_dict = request.__dict__["attribute_values"].copy()
    return RequestType(**normalize_to_json(request_dict))


@resolve_list_decorator(
    list_type_class=RequestListType,
    type_funct=get_request_type,
)
def resolve_request_list(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = info.context.get("partition_key")
    if not partition_key:
        raise ValueError("partition_key is required in context")

    search_mode = kwargs.get("search_mode")

    inquiry_funct = RequestModel.query
    count_funct = RequestModel.count
    args = [partition_key]

    if search_mode is not None:
        args.append(RequestModel.search_mode == search_mode)

    return inquiry_funct, count_funct, args


@insert_update_decorator(
    keys={"hash_key": "partition_key", "range_key": "request_uuid"},
    model_funct=get_request,
    count_funct=get_request_count,
    type_funct=get_request_type,
)
def insert_update_request(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = kwargs.get("partition_key")
    request_uuid = kwargs.get("request_uuid")

    if kwargs.get("entity") is None:
        cols = {
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }

        if not request_uuid:
            request_uuid = f"req-{pendulum.now('UTC').int_timestamp}-{uuid.uuid4().hex[:8]}"

        for key in [
            "user_query",
            "cypher_query",
            "search_mode",
            "results",
            "updated_by",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        cols["endpoint_id"] = info.context.get("endpoint_id")
        cols["part_id"] = info.context.get("part_id")

        RequestModel(partition_key, request_uuid, **cols).save()
        return

    request = kwargs.get("entity")

    actions = [
        RequestModel.updated_at.set(pendulum.now("UTC")),
    ]

    field_map = {
        "user_query": RequestModel.user_query,
        "cypher_query": RequestModel.cypher_query,
        "search_mode": RequestModel.search_mode,
        "results": RequestModel.results,
        "updated_by": RequestModel.updated_by,
    }

    for key, field in field_map.items():
        if key in kwargs:
            actions.append(field.set(None if kwargs[key] == "null" else kwargs[key]))

    request.update(actions=actions)


@delete_decorator(
    keys={"hash_key": "partition_key", "range_key": "request_uuid"},
    model_funct=get_request,
)
def delete_request(info: ResolveInfo, **kwargs: Any) -> bool:
    kwargs["entity"].delete()
    return True
