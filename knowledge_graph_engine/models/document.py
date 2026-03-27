# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import uuid
from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo
from pynamodb.attributes import (
    ListAttribute,
    NumberAttribute,
    UnicodeAttribute,
    UTCDateTimeAttribute,
)
from pynamodb.indexes import AllProjection, LocalSecondaryIndex

from silvaengine_dynamodb_base import (
    BaseModel,
    delete_decorator,
    insert_update_decorator,
    resolve_list_decorator,
)
from silvaengine_utility import method_cache

from ..handlers.config import Config
from ..types.document import DocumentListType, DocumentType
from ..utils.normalization import normalize_to_json


class DocumentUpdatedAtIndex(LocalSecondaryIndex):
    class Meta:
        index_name = "updated_at_index"
        projection = AllProjection()

    partition_key = UnicodeAttribute(hash_key=True)
    updated_at = UnicodeAttribute(range_key=True)


class DocumentExternalIdIndex(LocalSecondaryIndex):
    class Meta:
        index_name = "document_external_id_index"
        projection = AllProjection()

    partition_key = UnicodeAttribute(hash_key=True)
    document_external_id = UnicodeAttribute(range_key=True)


class DocumentModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "kge-documents"

    partition_key = UnicodeAttribute(hash_key=True)
    document_uuid = UnicodeAttribute(range_key=True)

    endpoint_id = UnicodeAttribute(null=True)
    part_id = UnicodeAttribute(null=True)

    document_source = UnicodeAttribute()
    document_external_id = UnicodeAttribute(null=True)
    chunk_index = NumberAttribute(default=0)
    document_title = UnicodeAttribute(null=True)
    content = UnicodeAttribute(null=True)
    content_embedding = ListAttribute(null=True)

    status = UnicodeAttribute(default="active")
    updated_by = UnicodeAttribute(null=True)
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()

    updated_at_index = DocumentUpdatedAtIndex()
    document_external_id_index = DocumentExternalIdIndex()


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("models", "document"),
    cache_enabled=Config.is_cache_enabled,
)
def get_document(partition_key: str, document_uuid: str) -> DocumentModel:
    return DocumentModel.get(partition_key, document_uuid)


def get_document_count(partition_key: str, document_uuid: str) -> int:
    return DocumentModel.count(
        partition_key, DocumentModel.document_uuid == document_uuid
    )


def get_document_type(info: ResolveInfo, document: DocumentModel) -> DocumentType:
    _ = info  # Keep for signature compatibility with decorators
    document_dict = document.__dict__["attribute_values"].copy()
    return DocumentType(**normalize_to_json(document_dict))


def resolve_document(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> Optional[DocumentType]:
    partition_key = info.context.get("partition_key")
    document_uuid = kwargs.get("document_uuid")

    if not partition_key or not document_uuid:
        return None

    return get_document(partition_key, document_uuid)


@resolve_list_decorator(
    list_type_class=DocumentListType,
    type_funct=get_document_type,
)
def resolve_document_list(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = info.context.get("partition_key")
    document_source = kwargs.get("document_source")
    document_external_id = kwargs.get("document_external_id")
    statuses = kwargs.get("statuses")
    updated_at_gt = kwargs.get("updated_at_gt")
    updated_at_lt = kwargs.get("updated_at_lt")

    args = []
    inquiry_funct = DocumentModel.scan
    count_funct = DocumentModel.count

    if partition_key:
        if updated_at_gt is not None and updated_at_lt is not None:
            range_key_condition = DocumentModel.updated_at.between(
                updated_at_gt, updated_at_lt
            )
        elif updated_at_gt is not None:
            range_key_condition = DocumentModel.updated_at > updated_at_gt
        elif updated_at_lt is not None:
            range_key_condition = DocumentModel.updated_at < updated_at_lt
        else:
            range_key_condition = None

        if document_external_id and range_key_condition is None:
            inquiry_funct = DocumentModel.document_external_id_index.query
            args = [
                partition_key,
                DocumentModel.document_external_id == document_external_id,
            ]
            count_funct = DocumentModel.document_external_id_index.count
        else:
            inquiry_funct = DocumentModel.updated_at_index.query
            count_funct = DocumentModel.updated_at_index.count
            args = [partition_key, range_key_condition]
    else:
        args = [partition_key] if partition_key else []

    the_filters = None
    if document_source:
        the_filters = DocumentModel.document_source == document_source
    if statuses:
        the_filters &= DocumentModel.status.is_in(*statuses)
    if the_filters:
        args.append(the_filters)

    return inquiry_funct, count_funct, args


@insert_update_decorator(
    keys={"hash_key": "partition_key", "range_key": "document_uuid"},
    range_key_required=True,
    model_funct=get_document,
    count_funct=get_document_count,
    type_funct=get_document_type,
)
def insert_update_document(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = kwargs.get("partition_key")
    document_uuid = kwargs.get("document_uuid")

    if kwargs.get("entity") is None:
        cols = {
            "document_source": kwargs.get("document_source", "unknown"),
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }

        if not document_uuid:
            cols["document_uuid"] = (
                f"doc-{pendulum.now('UTC').int_timestamp}-{str(uuid.uuid4())[:8]}"
            )
        else:
            cols["document_uuid"] = document_uuid

        for key in [
            "document_external_id",
            "chunk_index",
            "document_title",
            "content",
            "content_embedding",
            "status",
            "updated_by",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        cols["endpoint_id"] = info.context.get("endpoint_id")
        cols["part_id"] = info.context.get("part_id")

        DocumentModel(partition_key, cols["document_uuid"], **cols).save()
        return

    document = kwargs.get("entity")

    actions = [
        DocumentModel.updated_at.set(pendulum.now("UTC")),
    ]

    field_map = {
        "document_source": DocumentModel.document_source,
        "document_external_id": DocumentModel.document_external_id,
        "chunk_index": DocumentModel.chunk_index,
        "document_title": DocumentModel.document_title,
        "content": DocumentModel.content,
        "content_embedding": DocumentModel.content_embedding,
        "status": DocumentModel.status,
        "updated_by": DocumentModel.updated_by,
    }

    for key, field in field_map.items():
        if key in kwargs:
            actions.append(field.set(None if kwargs[key] == "null" else kwargs[key]))

    document.update(actions=actions)


@delete_decorator(
    keys={"hash_key": "partition_key", "range_key": "document_uuid"},
    model_funct=get_document,
)
def delete_document(info: ResolveInfo, **kwargs: Any) -> bool:
    kwargs["entity"].delete()
    return True
