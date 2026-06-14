# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any

from graphene import ResolveInfo

from ..handlers.search.handler import SearchHandler, RAGHandler


def resolve_search(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = info.context.get("partition_key")
    query_text = kwargs.get("query_text")

    if not partition_key or not query_text:
        return {"results": [], "total": 0}

    handler = SearchHandler(info)
    return handler.search(partition_key=partition_key, **kwargs)


def resolve_rag(info: ResolveInfo, **kwargs: Any) -> Any:
    partition_key = info.context.get("partition_key")
    query_text = kwargs.get("query_text")

    if not partition_key or not query_text:
        return {"answer": "", "context": []}

    handler = RAGHandler(info)
    return handler.rag(partition_key=partition_key, **kwargs)
