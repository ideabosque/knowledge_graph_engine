# -*- coding: utf-8 -*-
from __future__ import annotations, print_function

__author__ = "silvaengine"

import time
from typing import Any

from graphene import (
    DateTime,
    Field,
    Int,
    List,
    ObjectType,
    ResolveInfo,
    String,
)
from silvaengine_utility import JSONCamelCase

from ..mutations.document import DeleteDocument, InsertUpdateDocument
from ..mutations.extract import ExecuteExtract
from ..mutations.graph_schema import DeleteGraphSchema, InsertUpdateGraphSchema
from ..mutations.neo4j_instance import DeleteNeo4jInstance, InsertUpdateNeo4jInstance
from ..queries.document import resolve_document, resolve_document_list
from ..queries.graph_schema import resolve_graph_schema, resolve_graph_schema_list
from ..queries.search import resolve_rag, resolve_search
from ..types.document import DocumentListType, DocumentType
from ..types.graph_schema import GraphSchemaListType, GraphSchemaType
from ..types.neo4j_instance import Neo4jInstanceListType, Neo4jInstanceType
from ..types.request import RequestListType, RequestType
from ..types.search import ExtractResultType, RAGQueryResultType, SearchResultType


def type_class() -> list:
    return [
        DocumentType,
        DocumentListType,
        GraphSchemaType,
        GraphSchemaListType,
        Neo4jInstanceType,
        Neo4jInstanceListType,
        RequestType,
        RequestListType,
        ExtractResultType,
        SearchResultType,
        RAGQueryResultType,
    ]


class Query(ObjectType):
    ping = String()

    # --- CRUD queries ---
    document = Field(
        DocumentType,
        document_uuid=String(required=False),
    )

    document_list = Field(
        DocumentListType,
        page_number=Int(required=False),
        limit=Int(required=False),
        document_source=String(required=False),
        document_external_id=String(required=False),
        statuses=List(String, required=False),
        updated_at_gt=DateTime(required=False),
        updated_at_lt=DateTime(required=False),
    )

    graph_schema = Field(
        GraphSchemaType,
        schema_name=String(required=False),
    )

    graph_schema_list = Field(
        GraphSchemaListType,
        page_number=Int(required=False),
        limit=Int(required=False),
        schema_type=String(required=False),
        statuses=List(String, required=False),
        updated_at_gt=DateTime(required=False),
        updated_at_lt=DateTime(required=False),
    )

    neo4j_instance = Field(
        Neo4jInstanceType,
        instance_id=String(required=True),
    )

    neo4j_instance_list = Field(
        Neo4jInstanceListType,
        page_number=Int(required=False),
        limit=Int(required=False),
        statuses=List(String, required=False),
    )

    request = Field(
        RequestType,
        request_uuid=String(required=True),
    )

    request_list = Field(
        RequestListType,
        page_number=Int(required=False),
        limit=Int(required=False),
        search_mode=String(required=False),
    )

    # --- Knowledge graph queries ---
    search = Field(
        SearchResultType,
        query_text=String(required=True),
        search_type=String(required=False),
        search_mode=String(required=False),
        index_name=String(required=False),
        retrieval_query=String(required=False),
        filters=JSONCamelCase(required=False),
        top_k=Int(required=False),
        page=Int(required=False),
        limit=Int(required=False),
    )

    rag = Field(
        RAGQueryResultType,
        query_text=String(required=True),
        search_mode=String(required=False),
        index_name=String(required=False),
        top_k=Int(required=False),
        prompt=String(required=False),
    )

    # --- Resolvers ---

    def resolve_ping(self, info: ResolveInfo) -> str:
        return f"Hello at {time.strftime('%X')}!!"

    def resolve_document(self, info: ResolveInfo, **kwargs: Any) -> DocumentType | None:
        return resolve_document(info, **kwargs)

    def resolve_document_list(self, info: ResolveInfo, **kwargs: Any) -> DocumentListType:
        return resolve_document_list(info, **kwargs)

    def resolve_graph_schema(self, info: ResolveInfo, **kwargs: Any) -> GraphSchemaType | None:
        return resolve_graph_schema(info, **kwargs)

    def resolve_graph_schema_list(self, info: ResolveInfo, **kwargs: Any) -> GraphSchemaListType:
        return resolve_graph_schema_list(info, **kwargs)

    def resolve_neo4j_instance(self, info: ResolveInfo, **kwargs: Any) -> Neo4jInstanceType | None:
        from ..models.neo4j_instance import get_neo4j_instance, get_neo4j_instance_type

        partition_key = info.context.get("partition_key")
        instance_id = kwargs.get("instance_id")
        if not partition_key or not instance_id:
            return None
        try:
            instance = get_neo4j_instance(partition_key, instance_id)
            return get_neo4j_instance_type(info, instance)
        except Exception:
            return None

    def resolve_neo4j_instance_list(self, info: ResolveInfo, **kwargs: Any) -> Neo4jInstanceListType:
        from ..models.neo4j_instance import resolve_neo4j_instance_list as _resolve_neo4j_instance_list

        return _resolve_neo4j_instance_list(info, **kwargs)

    def resolve_request(self, info: ResolveInfo, **kwargs: Any) -> RequestType | None:
        from ..models.request import get_request, get_request_count, get_request_type

        partition_key = info.context.get("partition_key")
        request_uuid = kwargs.get("request_uuid")
        if not partition_key or not request_uuid:
            return None
        try:
            count = get_request_count(partition_key, request_uuid)
            if count == 0:
                return None
            return get_request_type(info, get_request(partition_key, request_uuid))
        except Exception:
            return None

    def resolve_request_list(self, info: ResolveInfo, **kwargs: Any) -> RequestListType:
        from ..models.request import resolve_request_list as _resolve_request_list

        return _resolve_request_list(info, **kwargs)

    def resolve_search(self, info: ResolveInfo, **kwargs: Any) -> SearchResultType:
        return resolve_search(info, **kwargs)

    def resolve_rag(self, info: ResolveInfo, **kwargs: Any) -> RAGQueryResultType:
        return resolve_rag(info, **kwargs)


class Mutations(ObjectType):
    insert_update_document = InsertUpdateDocument.Field()
    delete_document = DeleteDocument.Field()
    insert_update_graph_schema = InsertUpdateGraphSchema.Field()
    delete_graph_schema = DeleteGraphSchema.Field()
    insert_update_neo4j_instance = InsertUpdateNeo4jInstance.Field()
    delete_neo4j_instance = DeleteNeo4jInstance.Field()
    execute_extract = ExecuteExtract.Field()