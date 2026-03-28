# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from graphene import Field, Mutation, String
from silvaengine_utility import JSONCamelCase

from ..models.graph_schema import insert_update_graph_schema, delete_graph_schema
from ..types.graph_schema import GraphSchemaType


class InsertUpdateGraphSchema(Mutation):
    class Arguments:
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
        partition_key = info.context.get("partition_key")

        if not partition_key:
            raise ValueError("partition_key is required in context")

        kwargs["partition_key"] = partition_key
        insert_update_graph_schema(info, **kwargs)
        from ..models.graph_schema import get_graph_schema

        schema_name = kwargs.get("schema_name")
        return get_graph_schema(partition_key, schema_name)


class DeleteGraphSchema(Mutation):
    class Arguments:
        schema_name = String(required=True)

    Output = String

    @staticmethod
    def mutate(root, info, **kwargs):
        from ..models.graph_schema import get_graph_schema

        partition_key = info.context.get("partition_key")

        if not partition_key:
            raise ValueError("partition_key is required in context")

        schema_name = kwargs.get("schema_name")
        schema = get_graph_schema(partition_key, schema_name)
        delete_graph_schema(info, entity=schema)
        return "deleted"