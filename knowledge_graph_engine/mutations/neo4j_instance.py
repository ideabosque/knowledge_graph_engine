# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import traceback

from graphene import Int, Mutation, String

from ..models.repositories import get_repo
from ..types.neo4j_instance import Neo4jInstanceType
from ..handlers.config import Config


class InsertUpdateNeo4jInstance(Mutation):
    class Arguments:
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
        partition_key = info.context.get("partition_key")
        instance_id = kwargs.get("instance_id", "default")

        if not partition_key:
            raise ValueError("partition_key is required in context")

        try:
            repo = get_repo("neo4j_instance")
            repo.insert_update(info, **kwargs)
            return repo.resolve_single(info, instance_id=instance_id)
        except Exception as e:
            logger.error(f"InsertUpdateNeo4jInstance error: {traceback.format_exc()}")
            raise e


class DeleteNeo4jInstance(Mutation):
    class Arguments:
        instance_id = String(required=True)

    Output = String

    @staticmethod
    def mutate(root, info, **kwargs):
        logger = Config.get_logger()
        partition_key = info.context.get("partition_key")
        instance_id = kwargs.get("instance_id")

        if not partition_key:
            raise ValueError("partition_key is required in context")

        try:
            repo = get_repo("neo4j_instance")
            data = repo.get(partition_key=partition_key, instance_id=instance_id)
            if data:
                repo.delete(info, partition_key=partition_key, instance_id=instance_id)
            return "deleted"
        except Exception as e:
            logger.error(f"DeleteNeo4jInstance error: {traceback.format_exc()}")
            raise e