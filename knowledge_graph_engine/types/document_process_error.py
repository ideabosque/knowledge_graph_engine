# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from graphene import DateTime, Int, List, ObjectType, String
from silvaengine_dynamodb_base import ListObjectType


class DocumentProcessErrorType(ObjectType):
    partition_key = String()
    process_error_uuid = String()

    document_source = String()
    document_external_id = String()
    chunk_index = Int()
    error_message = String()
    process_status = String()
    process_count = Int()

    created_at = DateTime()
    updated_at = DateTime()


class DocumentProcessErrorListType(ListObjectType):
    document_process_error_list = List(DocumentProcessErrorType)
