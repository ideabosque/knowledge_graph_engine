# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from graphene import Field, Mutation, String
from silvaengine_utility import JSONCamelCase

from ..models.graph_schema import insert_update_graph_schema, delete_graph_schema
from ..types.graph_schema import GraphSchemaType


class InsertUpdateGraphSchema(Mutation):
    class Arguments:
        partition_key = String(required=True)
        schema_name = String(required=True)
        schema_type = String()
        schema_definition = JSONCamelCase()
        source_text_hash = String()
        neo4j_schema_string = String()
        status = String()
        updated_by = String()

    Output = GraphSchemaType

    @staticmethod
    def mutate(root, info, **kwargs):
        insert_update_graph_schema(info, **kwargs)
        from ..models.graph_schema import get_graph_schema

        partition_key = kwargs.get("partition_key")
        schema_name = kwargs.get("schema_name")
        return get_graph_schema(partition_key, schema_name)


class DeleteGraphSchema(Mutation):
    class Arguments:
        partition_key = String(required=True)
        schema_name = String(required=True)

    Output = String

    @staticmethod
    def mutate(root, info, **kwargs):
        from ..models.graph_schema import get_graph_schema

        partition_key = kwargs.get("partition_key")
        schema_name = kwargs.get("schema_name")
        schema = get_graph_schema(partition_key, schema_name)
        delete_graph_schema(info, entity=schema)
        return "deleted"