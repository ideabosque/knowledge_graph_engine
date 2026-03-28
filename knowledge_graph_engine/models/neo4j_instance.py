# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import uuid
from typing import Any, Dict

import pendulum
from graphene import ResolveInfo
from pynamodb.attributes import (
    MapAttribute,
    NumberAttribute,
    UnicodeAttribute,
    UTCDateTimeAttribute,
)
from ..types.neo4j_instance import Neo4jInstanceListType, Neo4jInstanceType
from ..utils.normalization import normalize_to_json
from silvaengine_dynamodb_base import (
    BaseModel,
    delete_decorator,
    insert_update_decorator,
    resolve_list_decorator,
)
from silvaengine_utility import method_cache

from ..handlers.config import Config


class Neo4jInstanceModel(BaseModel):
    """Registry of Neo4j instances, one per partition (tenant)."""

    class Meta(BaseModel.Meta):
        table_name = "kge-neo4j_instances"

    partition_key = UnicodeAttribute(hash_key=True)
    instance_id = UnicodeAttribute(range_key=True)

    endpoint_id = UnicodeAttribute(null=True)
    part_id = UnicodeAttribute(null=True)

    neo4j_uri = UnicodeAttribute()
    neo4j_username = UnicodeAttribute(default="neo4j")
    neo4j_password = UnicodeAttribute()
    neo4j_database = UnicodeAttribute(default="neo4j")

    container_id = UnicodeAttribute(null=True)
    status = UnicodeAttribute(default="active")
    max_connection_pool_size = NumberAttribute(default=5)

    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()


@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("models", "neo4j_instance"),
    cache_enabled=Config.is_cache_enabled,
)
def get_neo4j_instance(partition_key: str, instance_id: str) -> Neo4jInstanceModel:
    return Neo4jInstanceModel.get(partition_key, instance_id)


def get_active_neo4j_instance(partition_key: str) -> Neo4jInstanceModel:
    """Get the active Neo4j instance for a partition. Raises if none found."""
    for instance in Neo4jInstanceModel.query(
        partition_key,
        filter_condition=Neo4jInstanceModel.status == "active",
    ):
        return instance
    raise Neo4jInstanceModel.DoesNotExist(
        f"No active Neo4j instance for partition: {partition_key}"
    )


def get_neo4j_instance_count(partition_key: str, instance_id: str) -> int:
    return Neo4jInstanceModel.count(
        partition_key, Neo4jInstanceModel.instance_id == instance_id
    )


def get_neo4j_instance_type(
    info: ResolveInfo, instance: Neo4jInstanceModel
) -> Neo4jInstanceType:
    _ = info  # Keep for signature compatibility with decorators
    instance_dict = instance.__dict__["attribute_values"].copy()
    return Neo4jInstanceType(**normalize_to_json(instance_dict))


@resolve_list_decorator(
    list_type_class=Neo4jInstanceListType,
    type_funct=get_neo4j_instance_type,
)
def resolve_neo4j_instance_list(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = info.context.get("partition_key")
    statuses = kwargs.get("statuses")

    the_filters = None
    if statuses:
        the_filters = Neo4jInstanceModel.status.is_in(*statuses)

    if partition_key:
        inquiry_funct = Neo4jInstanceModel.query
        count_funct = Neo4jInstanceModel.count
        args = [partition_key]
    else:
        inquiry_funct = Neo4jInstanceModel.scan
        count_funct = Neo4jInstanceModel.count
        args = []

    if the_filters:
        args.append(the_filters)

    return inquiry_funct, count_funct, args


def _deactivate_current_active_instance(partition_key: str, exclude_instance_id: str = None):
    """Deactivate the currently active instance for a partition, optionally excluding one.
    Also closes the cached Neo4j driver so the new active instance is picked up.
    """
    from ..handlers.neo4j_connection_manager import Neo4jConnectionManager

    for instance in Neo4jInstanceModel.query(
        partition_key,
        filter_condition=Neo4jInstanceModel.status == "active",
    ):
        if exclude_instance_id and instance.instance_id == exclude_instance_id:
            continue
        instance.update(actions=[
            Neo4jInstanceModel.status.set("inactive"),
            Neo4jInstanceModel.updated_at.set(pendulum.now("UTC")),
        ])
    # Close cached driver so the next request picks up the new active instance
    Neo4jConnectionManager.close_driver(partition_key)


@insert_update_decorator(
    keys={"hash_key": "partition_key", "range_key": "instance_id"},
    model_funct=get_neo4j_instance,
    count_funct=get_neo4j_instance_count,
    type_funct=get_neo4j_instance_type,
    range_key_required=True,
)
def insert_update_neo4j_instance(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = kwargs.get("partition_key")
    instance_id = kwargs.get("instance_id", "default")

    if kwargs.get("entity") is None:
        # New insert: default status is "active", so deactivate current active
        new_status = kwargs.get("status", "active")
        if new_status == "active":
            _deactivate_current_active_instance(partition_key)

        cols = {
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }

        for key in [
            "neo4j_uri",
            "neo4j_username",
            "neo4j_password",
            "neo4j_database",
            "container_id",
            "status",
            "max_connection_pool_size",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        cols["endpoint_id"] = info.context.get("endpoint_id")
        cols["part_id"] = info.context.get("part_id")

        Neo4jInstanceModel(partition_key, instance_id, **cols).save()
        return

    instance = kwargs.get("entity")

    # If activating this instance, deactivate all others first
    if kwargs.get("status") == "active":
        _deactivate_current_active_instance(partition_key, exclude_instance_id=instance.instance_id)

    actions = [
        Neo4jInstanceModel.updated_at.set(pendulum.now("UTC")),
    ]

    field_map = {
        "neo4j_uri": Neo4jInstanceModel.neo4j_uri,
        "neo4j_username": Neo4jInstanceModel.neo4j_username,
        "neo4j_password": Neo4jInstanceModel.neo4j_password,
        "neo4j_database": Neo4jInstanceModel.neo4j_database,
        "container_id": Neo4jInstanceModel.container_id,
        "status": Neo4jInstanceModel.status,
        "max_connection_pool_size": Neo4jInstanceModel.max_connection_pool_size,
    }

    for key, field in field_map.items():
        if key in kwargs:
            actions.append(field.set(None if kwargs[key] == "null" else kwargs[key]))

    instance.update(actions=actions)


@delete_decorator(
    keys={"hash_key": "partition_key", "range_key": "instance_id"},
    model_funct=get_neo4j_instance,
)
def delete_neo4j_instance(info: ResolveInfo, **kwargs: Any) -> bool:
    kwargs["entity"].delete()
    return True
