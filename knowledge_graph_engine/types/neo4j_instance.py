# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from graphene import DateTime, Int, List, ObjectType, String
from silvaengine_dynamodb_base import ListObjectType


class Neo4jInstanceType(ObjectType):
    partition_key = String()
    instance_id = String()

    endpoint_id = String()
    part_id = String()

    neo4j_uri = String()
    neo4j_username = String()
    neo4j_password = String()
    neo4j_database = String()

    container_id = String()
    status = String()
    max_connection_pool_size = Int()

    created_at = DateTime()
    updated_at = DateTime()


class Neo4jInstanceListType(ListObjectType):
    neo4j_instance_list = List(Neo4jInstanceType)