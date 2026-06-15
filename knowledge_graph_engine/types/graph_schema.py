# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from graphene import DateTime, Field, Int, List, ObjectType, String
from silvaengine_dynamodb_base import ListObjectType
from silvaengine_utility import JSONCamelCase


class GraphSchemaType(ObjectType):
    partition_key = String()
    schema_name = String()

    endpoint_id = String()
    part_id = String()

    schema_type = String()
    schema_definition = Field(JSONCamelCase)
    source_text_hash = String()
    neo4j_schema_string = String()
    text2cypher_examples = String()

    status = String()
    updated_by = String()
    created_at = DateTime()
    updated_at = DateTime()


class GraphSchemaListType(ListObjectType):
    graph_schema_list = List(GraphSchemaType)