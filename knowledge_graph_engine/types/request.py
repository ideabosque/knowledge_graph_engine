# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from graphene import DateTime, List, ObjectType, String
from silvaengine_dynamodb_base import ListObjectType
from silvaengine_utility import JSONCamelCase


class RequestType(ObjectType):
    partition_key = String()
    request_uuid = String()

    endpoint_id = String()
    part_id = String()

    user_query = String()
    cypher_query = String()
    search_mode = String()
    results = List(JSONCamelCase)

    updated_by = String()
    created_at = DateTime()
    updated_at = DateTime()


class RequestListType(ListObjectType):
    request_list = List(RequestType)