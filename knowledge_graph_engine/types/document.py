# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from graphene import DateTime, Field, Int, List, ObjectType, String
from promise import Promise
from silvaengine_dynamodb_base import ListObjectType
from silvaengine_utility import JSONCamelCase


class DocumentType(ObjectType):
    partition_key = String()
    document_uuid = String()

    endpoint_id = String()
    part_id = String()

    document_source = String()
    document_external_id = String()
    chunk_index = Int()
    document_title = String()
    content = String()
    content_embedding = List(String)

    status = String()
    updated_by = String()
    created_at = DateTime()
    updated_at = DateTime()


class DocumentListType(ListObjectType):
    document_list = List(DocumentType)