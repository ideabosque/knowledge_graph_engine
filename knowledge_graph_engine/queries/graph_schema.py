# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from graphene import ResolveInfo

from ..models.graph_schema import (
    resolve_graph_schema as _resolve_graph_schema,
    resolve_graph_schema_list as _resolve_graph_schema_list,
)
from ..types.graph_schema import GraphSchemaListType, GraphSchemaType


def resolve_graph_schema(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> Optional[GraphSchemaType]:
    return _resolve_graph_schema(info, **kwargs)


def resolve_graph_schema_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> GraphSchemaListType:
    return _resolve_graph_schema_list(info, **kwargs)
