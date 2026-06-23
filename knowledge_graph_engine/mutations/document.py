# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import traceback

from graphene import Int, Mutation, String

from ..models.repositories import get_repo
from ..types.document import DocumentType
from ..handlers.config import Config


class InsertUpdateDocument(Mutation):
    class Arguments:
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
        partition_key = info.context.get("partition_key")

        if not partition_key:
            raise ValueError("partition_key is required in context")

        try:
            repo = get_repo("document")
            repo.insert_update(info, **kwargs)
            document_uuid = kwargs.get("document_uuid")
            return repo.resolve_single(info, document_uuid=document_uuid)
        except Exception as e:
            logger.error(f"InsertUpdateDocument error: {traceback.format_exc()}")
            raise e


class DeleteDocument(Mutation):
    class Arguments:
        document_uuid = String(required=True)

    Output = String

    @staticmethod
    def mutate(root, info, **kwargs):
        logger = Config.get_logger()
        partition_key = info.context.get("partition_key")
        document_uuid = kwargs.get("document_uuid")

        if not partition_key:
            raise ValueError("partition_key is required in context")

        try:
            repo = get_repo("document")
            data = repo.get(partition_key=partition_key, document_uuid=document_uuid)
            if data:
                repo.delete(info, partition_key=partition_key, document_uuid=document_uuid)
            return "deleted"
        except Exception as e:
            logger.error(f"DeleteDocument error: {traceback.format_exc()}")
            raise e