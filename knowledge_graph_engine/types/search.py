# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from graphene import Field, Float, Int, List, ObjectType, String
from silvaengine_utility import JSONCamelCase


class SearchResultItemType(ObjectType):
    content = String()
    score = Float()
    metadata = Field(JSONCamelCase)


class SearchResultType(ObjectType):
    results = List(JSONCamelCase)
    query = String()
    total = Int()
    page = Int()
    limit = Int()


class RAGQueryResultType(ObjectType):
    answer = String()
    sources = List(JSONCamelCase)
    context = List(JSONCamelCase)


class ExtractResultType(ObjectType):
    status = String()
    partition_key = String()
    document_uuid = String()
    schema_name = String()
    entities_extracted = Int()
    relationships_extracted = Int()
    result = Field(JSONCamelCase)
