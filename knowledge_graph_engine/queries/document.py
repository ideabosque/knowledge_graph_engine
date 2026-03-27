# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from graphene import ResolveInfo

from ..models.document import (
    resolve_document as _resolve_document,
    resolve_document_list as _resolve_document_list,
)
from ..types.document import DocumentListType, DocumentType


def resolve_document(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> Optional[DocumentType]:
    return _resolve_document(info, **kwargs)


def resolve_document_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> DocumentListType:
    return _resolve_document_list(info, **kwargs)
