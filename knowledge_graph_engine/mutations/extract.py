# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import traceback

from graphene import Mutation, String
from silvaengine_utility import JSONCamelCase

from ..types.search import ExtractResultType


class ExecuteExtract(Mutation):
    class Arguments:
        partition_key = String(required=True)
        text = String(required=True)
        graph_schema = JSONCamelCase()
        schema_name = String()
        document_source = String()
        document_external_id = String()

    Output = ExtractResultType

    @staticmethod
    def mutate(root, info, **kwargs):
        partition_key = kwargs.get("partition_key")
        text = kwargs.get("text")
        graph_schema = kwargs.get("graph_schema")
        schema_name = kwargs.get("schema_name")

        # Get partition_key from context if not provided
        if not partition_key and info and hasattr(info, "context"):
            partition_key = info.context.get("partition_key")

        if not partition_key:
            raise ValueError("partition_key is required")

        if not text:
            raise ValueError("text is required")

        from ..handlers.config import Config
        from ..handlers.extractor import Extractor

        logger = Config.get_logger()
        extractor = Extractor(info)

        try:
            result = extractor.extract(
                partition_key=partition_key,
                text=text,
                graph_schema=graph_schema,
                schema_name=schema_name,
                document_source=kwargs.get("document_source"),
                document_external_id=kwargs.get("document_external_id"),
            )
            return ExtractResultType(**result)
        except Exception as e:
            logger.error(f"Extract error: {traceback.format_exc()}")
            raise e