# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import traceback

from graphene import Mutation, String
from silvaengine_utility import JSONCamelCase

from ..types.search import ExtractResultType


class ExecuteExtract(Mutation):
    class Arguments:
        text = String(required=True)
        graph_schema = JSONCamelCase()
        document_source = String()
        document_external_id = String()

    Output = ExtractResultType

    @staticmethod
    def mutate(root, info, **kwargs):
        partition_key = info.context.get("partition_key")
        text = kwargs.get("text")
        graph_schema = kwargs.get("graph_schema")

        if not partition_key:
            raise ValueError("partition_key is required in context")

        if not text:
            raise ValueError("text is required")

        from ..handlers.config import Config
        from ..handlers.extraction.handler import Extractor

        logger = Config.get_logger()
        extractor = Extractor(info)

        try:
            result = extractor.extract(
                partition_key=partition_key,
                text=text,
                graph_schema=graph_schema,
                document_source=kwargs.get("document_source"),
                document_external_id=kwargs.get("document_external_id"),
            )
            return ExtractResultType(**result)
        except Exception as e:
            logger.error(f"Extract error: {traceback.format_exc()}")
            raise e