# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import uuid
from typing import Any, Dict

import pendulum
from graphene import ResolveInfo
from pynamodb.attributes import NumberAttribute, UnicodeAttribute, UTCDateTimeAttribute

from silvaengine_dynamodb_base import BaseModel, delete_decorator, insert_update_decorator
from silvaengine_utility import method_cache

from ...handlers.config import Config
from ...types.document_process_error import DocumentProcessErrorType
from ...utils.normalization import normalize_to_json

class DocumentProcessErrorModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "kge-document_process_errors"

    partition_key = UnicodeAttribute(hash_key=True)
    process_error_uuid = UnicodeAttribute(range_key=True)

    document_source = UnicodeAttribute()
    document_external_id = UnicodeAttribute(null=True)
    chunk_index = NumberAttribute(null=True)
    error_message = UnicodeAttribute(null=True)
    process_status = UnicodeAttribute(default="failed")
    process_count = NumberAttribute(default=0)

    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("models", "document_process_error"),
    cache_enabled=Config.is_cache_enabled,
)
def get_document_process_error(partition_key: str, process_error_uuid: str) -> DocumentProcessErrorModel:
    return DocumentProcessErrorModel.get(partition_key, process_error_uuid)


def get_document_process_error_count(partition_key: str, process_error_uuid: str) -> int:
    return DocumentProcessErrorModel.count(
        partition_key, DocumentProcessErrorModel.process_error_uuid == process_error_uuid
    )


def get_document_process_error_type(info: ResolveInfo, error: DocumentProcessErrorModel) -> DocumentProcessErrorType:
    _ = info  # Keep for signature compatibility with decorators
    error_dict = error.__dict__["attribute_values"].copy()
    return DocumentProcessErrorType(**normalize_to_json(error_dict))


@insert_update_decorator(
    keys={"hash_key": "partition_key", "range_key": "process_error_uuid"},
    model_funct=get_document_process_error,
    count_funct=get_document_process_error_count,
    type_funct=get_document_process_error_type,
)
def insert_update_document_process_error(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = kwargs.get("partition_key")
    process_error_uuid = kwargs.get("process_error_uuid")

    if kwargs.get("entity") is None:
        cols = {
            "document_source": kwargs.get("document_source", "unknown"),
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }

        if not process_error_uuid:
            cols["process_error_uuid"] = f"err-{pendulum.now('UTC').int_timestamp}-{str(uuid.uuid4())[:8]}"
        else:
            cols["process_error_uuid"] = process_error_uuid

        for key in [
            "document_external_id",
            "chunk_index",
            "error_message",
            "process_status",
            "process_count",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        DocumentProcessErrorModel(partition_key, cols["process_error_uuid"], **cols).save()
        return

    error = kwargs.get("entity")

    actions = [
        DocumentProcessErrorModel.updated_at.set(pendulum.now("UTC")),
    ]

    field_map = {
        "document_source": DocumentProcessErrorModel.document_source,
        "document_external_id": DocumentProcessErrorModel.document_external_id,
        "chunk_index": DocumentProcessErrorModel.chunk_index,
        "error_message": DocumentProcessErrorModel.error_message,
        "process_status": DocumentProcessErrorModel.process_status,
        "process_count": DocumentProcessErrorModel.process_count,
    }

    for key, field in field_map.items():
        if key in kwargs:
            actions.append(field.set(None if kwargs[key] == "null" else kwargs[key]))

    error.update(actions=actions)


@delete_decorator(
    keys={"hash_key": "partition_key", "range_key": "process_error_uuid"},
    model_funct=get_document_process_error,
)
def delete_document_process_error(info: ResolveInfo, **kwargs: Any) -> bool:
    kwargs["entity"].delete()
    return True