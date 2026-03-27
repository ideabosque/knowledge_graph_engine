# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import traceback

from graphene import Field, Int, Mutation, String
from silvaengine_utility import JSONCamelCase

from ..models.document import insert_update_document, delete_document, get_document
from ..types.document import DocumentType
from ..handlers.config import Config


class InsertUpdateDocument(Mutation):
    class Arguments:
        partition_key = String(required=True)
        document_uuid = String()
        document_source = String()
        document_external_id = String()
        chunk_index = Int()
        document_title = String()
        content = String()
        content_embedding = String()
        status = String()
        updated_by = String(required=True)

    Output = DocumentType

    @staticmethod
    def mutate(root, info, **kwargs):
        logger = Config.get_logger()
        partition_key = kwargs.get("partition_key")
        
        # Get partition_key from context if not provided
        if not partition_key and hasattr(info, "context"):
            partition_key = info.context.get("partition_key")
        
        if not partition_key:
            raise ValueError("partition_key is required")
        
        try:
            insert_update_document(info, **kwargs)
            document_uuid = kwargs.get("document_uuid")
            return get_document(partition_key, document_uuid)
        except Exception as e:
            logger.error(f"InsertUpdateDocument error: {traceback.format_exc()}")
            raise e


class DeleteDocument(Mutation):
    class Arguments:
        partition_key = String(required=True)
        document_uuid = String(required=True)

    Output = String

    @staticmethod
    def mutate(root, info, **kwargs):
        logger = Config.get_logger()
        partition_key = kwargs.get("partition_key")
        document_uuid = kwargs.get("document_uuid")
        
        # Get partition_key from context if not provided
        if not partition_key and hasattr(info, "context"):
            partition_key = info.context.get("partition_key")
        
        if not partition_key:
            raise ValueError("partition_key is required")
        
        try:
            document = get_document(partition_key, document_uuid)
            delete_document(info, entity=document)
            return "deleted"
        except Exception as e:
            logger.error(f"DeleteDocument error: {traceback.format_exc()}")
            raise e