# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from graphene import ResolveInfo

from ..models.repositories import get_repo
from ..types.graph_schema import GraphSchemaListType, GraphSchemaType


def resolve_graph_schema(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> Optional[GraphSchemaType]:
    repo = get_repo("graph_schema")
    return repo.resolve_single(info, **kwargs)


def resolve_graph_schema_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> GraphSchemaListType:
    repo = get_repo("graph_schema")
    return repo.list(info, **kwargs)