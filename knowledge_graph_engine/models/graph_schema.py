# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

import pendulum
from graphene import ResolveInfo
from pynamodb.attributes import MapAttribute, UnicodeAttribute, UTCDateTimeAttribute
from pynamodb.indexes import AllProjection, LocalSecondaryIndex

from silvaengine_dynamodb_base import (
    BaseModel,
    delete_decorator,
    insert_update_decorator,
    resolve_list_decorator,
)
from silvaengine_utility import method_cache
from ..types.graph_schema import GraphSchemaListType, GraphSchemaType
from ..utils.normalization import normalize_to_json
from ..handlers.config import Config


class GraphSchemaUpdatedAtIndex(LocalSecondaryIndex):
    class Meta:
        index_name = "updated_at_index"
        projection = AllProjection()

    partition_key = UnicodeAttribute(hash_key=True)
    updated_at = UTCDateTimeAttribute(range_key=True)


class GraphSchemaModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "kge-graph_schemas"

    partition_key = UnicodeAttribute(hash_key=True)
    schema_name = UnicodeAttribute(range_key=True)

    endpoint_id = UnicodeAttribute(null=True)
    part_id = UnicodeAttribute(null=True)

    schema_type = UnicodeAttribute()
    schema_definition = MapAttribute()
    source_text_hash = UnicodeAttribute(null=True)
    neo4j_schema_string = UnicodeAttribute(null=True)

    status = UnicodeAttribute(default="active")
    updated_by = UnicodeAttribute(null=True)
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()

    updated_at_index = GraphSchemaUpdatedAtIndex()


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("models", "graph_schema"),
    cache_enabled=Config.is_cache_enabled,
)
def get_graph_schema(partition_key: str, schema_name: str) -> GraphSchemaModel:
    return GraphSchemaModel.get(partition_key, schema_name)


def get_active_graph_schema(partition_key: str) -> GraphSchemaModel:
    """Get the active graph schema for a partition. Raises if none found."""
    active_schemas = list(
        GraphSchemaModel.query(
            partition_key,
            filter_condition=GraphSchemaModel.status == "active",
        )
    )
    if active_schemas:
        if len(active_schemas) > 1:
            Config.get_logger().warning(
                "Multiple active graph schemas found for partition %s; choosing the most recently updated one.",
                partition_key,
            )
        return max(active_schemas, key=lambda item: item.updated_at or item.created_at)
    raise GraphSchemaModel.DoesNotExist(
        f"No active graph schema for partition: {partition_key}"
    )


def get_graph_schema_count(partition_key: str, schema_name: str) -> int:
    return GraphSchemaModel.count(partition_key, GraphSchemaModel.schema_name == schema_name)


def get_graph_schema_type(info: ResolveInfo, schema: GraphSchemaModel) -> GraphSchemaType:
    _ = info  # Keep for signature compatibility with decorators
    schema_dict = schema.__dict__["attribute_values"].copy()
    if schema_dict.get("schema_definition") is None:
        schema_dict["schema_definition"] = {}
    return GraphSchemaType(**normalize_to_json(schema_dict))


def resolve_graph_schema(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> Optional[GraphSchemaType]:
    partition_key = info.context.get("partition_key")
    schema_name = kwargs.get("schema_name")

    if not partition_key or not schema_name:
        return None

    return get_graph_schema_type(info, get_graph_schema(partition_key, schema_name))


def get_graph_schemas_for_partition(partition_key: str) -> list:
    """Get all schemas for a partition (tenant)."""
    return list(GraphSchemaModel.query(partition_key))


@resolve_list_decorator(
    list_type_class=GraphSchemaListType,
    type_funct=get_graph_schema_type,
)
def resolve_graph_schema_list(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = info.context.get("partition_key")
    schema_type = kwargs.get("schema_type")
    statuses = kwargs.get("statuses")
    updated_at_gt = kwargs.get("updated_at_gt")
    updated_at_lt = kwargs.get("updated_at_lt")

    args = []
    inquiry_funct = GraphSchemaModel.scan
    count_funct = GraphSchemaModel.count

    if partition_key:
        if updated_at_gt is not None and updated_at_lt is not None:
            range_key_condition = GraphSchemaModel.updated_at.between(
                updated_at_gt, updated_at_lt
            )
        elif updated_at_gt is not None:
            range_key_condition = GraphSchemaModel.updated_at > updated_at_gt
        elif updated_at_lt is not None:
            range_key_condition = GraphSchemaModel.updated_at < updated_at_lt
        else:
            range_key_condition = None

        inquiry_funct = GraphSchemaModel.updated_at_index.query
        count_funct = GraphSchemaModel.updated_at_index.count
        args = [partition_key, range_key_condition]
    else:
        args = [partition_key] if partition_key else []

    the_filters = None
    if schema_type:
        the_filters = GraphSchemaModel.schema_type == schema_type
    if statuses:
        status_filter = GraphSchemaModel.status.is_in(*statuses)
        the_filters = status_filter if the_filters is None else the_filters & status_filter
    if the_filters is not None:
        args.append(the_filters)

    return inquiry_funct, count_funct, args


def _deactivate_current_active_schema(partition_key: str, exclude_schema_name: str = None):
    """Deactivate the currently active schema for a partition, optionally excluding one."""
    for schema in GraphSchemaModel.query(
        partition_key,
        filter_condition=GraphSchemaModel.status == "active",
    ):
        if exclude_schema_name and schema.schema_name == exclude_schema_name:
            continue
        schema.update(actions=[
            GraphSchemaModel.status.set("inactive"),
            GraphSchemaModel.updated_at.set(pendulum.now("UTC")),
        ])


@insert_update_decorator(
    keys={"hash_key": "partition_key", "range_key": "schema_name"},
    model_funct=get_graph_schema,
    count_funct=get_graph_schema_count,
    type_funct=get_graph_schema_type,
)
def insert_update_graph_schema(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = kwargs.get("partition_key")
    schema_name = kwargs.get("schema_name")

    if kwargs.get("entity") is None:
        # New insert: default status is "active", so deactivate current active
        new_status = kwargs.get("status", "active")
        if new_status == "active":
            _deactivate_current_active_schema(partition_key)

        cols = {
            "schema_type": kwargs.get("schema_type", "auto"),
            "schema_definition": kwargs.get("schema_definition", {}),
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }

        for key in [
            "source_text_hash",
            "neo4j_schema_string",
            "status",
            "updated_by",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        cols["endpoint_id"] = info.context.get("endpoint_id")
        cols["part_id"] = info.context.get("part_id")

        GraphSchemaModel(partition_key, schema_name, **cols).save()
        return

    schema = kwargs.get("entity")

    # If activating this schema, deactivate all others first
    if kwargs.get("status") == "active":
        _deactivate_current_active_schema(partition_key, exclude_schema_name=schema.schema_name)

    actions = [
        GraphSchemaModel.updated_at.set(pendulum.now("UTC")),
    ]

    field_map = {
        "schema_type": GraphSchemaModel.schema_type,
        "schema_definition": GraphSchemaModel.schema_definition,
        "source_text_hash": GraphSchemaModel.source_text_hash,
        "neo4j_schema_string": GraphSchemaModel.neo4j_schema_string,
        "status": GraphSchemaModel.status,
        "updated_by": GraphSchemaModel.updated_by,
    }

    for key, field in field_map.items():
        if key in kwargs:
            actions.append(field.set(None if kwargs[key] == "null" else kwargs[key]))

    schema.update(actions=actions)


@delete_decorator(
    keys={"hash_key": "partition_key", "range_key": "schema_name"},
    model_funct=get_graph_schema,
)
def delete_graph_schema(info: ResolveInfo, **kwargs: Any) -> bool:
    kwargs["entity"].delete()
    return True
