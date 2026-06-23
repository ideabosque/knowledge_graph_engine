# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from graphene import Mutation, String
from silvaengine_utility import JSONCamelCase

from ..models.repositories import get_repo
from ..types.graph_schema import GraphSchemaType


class InsertUpdateGraphSchema(Mutation):
    class Arguments:
        schema_name = String(required=True)
        schema_type = String()
        schema_definition = JSONCamelCase()
        source_text_hash = String()
        neo4j_schema_string = String()
        text2cypher_examples = String()
        status = String()
        updated_by = String()

    Output = GraphSchemaType

    @staticmethod
    def mutate(root, info, **kwargs):
        partition_key = info.context.get("partition_key")

        if not partition_key:
            raise ValueError("partition_key is required in context")

        kwargs["partition_key"] = partition_key
        repo = get_repo("graph_schema")
        repo.insert_update(info, **kwargs)
        schema_name = kwargs.get("schema_name")
        return repo.resolve_single(info, schema_name=schema_name)


class DeleteGraphSchema(Mutation):
    class Arguments:
        schema_name = String(required=True)

    Output = String

    @staticmethod
    def mutate(root, info, **kwargs):
        partition_key = info.context.get("partition_key")

        if not partition_key:
            raise ValueError("partition_key is required in context")

        schema_name = kwargs.get("schema_name")
        repo = get_repo("graph_schema")
        data = repo.get(partition_key=partition_key, schema_name=schema_name)
        if data:
            repo.delete(info, partition_key=partition_key, schema_name=schema_name)
        return "deleted"