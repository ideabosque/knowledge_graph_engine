# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import traceback

from graphene import Field, Int, Mutation, String

from ..models.neo4j_instance import (
    insert_update_neo4j_instance,
    delete_neo4j_instance,
    get_neo4j_instance,
)
from ..types.neo4j_instance import Neo4jInstanceType
from ..handlers.config import Config


class InsertUpdateNeo4jInstance(Mutation):
    class Arguments:
        partition_key = String(required=True)
        instance_id = String()
        neo4j_uri = String(required=True)
        neo4j_username = String()
        neo4j_password = String(required=True)
        neo4j_database = String()
        container_id = String()
        status = String()
        max_connection_pool_size = Int()

    Output = Neo4jInstanceType

    @staticmethod
    def mutate(root, info, **kwargs):
        logger = Config.get_logger()
        partition_key = kwargs.get("partition_key")
        instance_id = kwargs.get("instance_id", "default")
        
        # Get partition_key from context if not provided
        if not partition_key and hasattr(info, "context"):
            partition_key = info.context.get("partition_key")
        
        if not partition_key:
            raise ValueError("partition_key is required")
        
        try:
            insert_update_neo4j_instance(info, **kwargs)
            return get_neo4j_instance(partition_key, instance_id)
        except Exception as e:
            logger.error(f"InsertUpdateNeo4jInstance error: {traceback.format_exc()}")
            raise e


class DeleteNeo4jInstance(Mutation):
    class Arguments:
        partition_key = String(required=True)
        instance_id = String(required=True)

    Output = String

    @staticmethod
    def mutate(root, info, **kwargs):
        logger = Config.get_logger()
        partition_key = kwargs.get("partition_key")
        instance_id = kwargs.get("instance_id")
        
        # Get partition_key from context if not provided
        if not partition_key and hasattr(info, "context"):
            partition_key = info.context.get("partition_key")
        
        if not partition_key:
            raise ValueError("partition_key is required")
        
        try:
            instance = get_neo4j_instance(partition_key, instance_id)
            delete_neo4j_instance(info, entity=instance)
            return "deleted"
        except Exception as e:
            logger.error(f"DeleteNeo4jInstance error: {traceback.format_exc()}")
            raise e