# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from graphene import ResolveInfo

from ..models.repositories import get_repo
from ..types.document import DocumentListType, DocumentType


def resolve_document(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> Optional[DocumentType]:
    repo = get_repo("document")
    return repo.resolve_single(info, **kwargs)


def resolve_document_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> DocumentListType:
    repo = get_repo("document")
    return repo.list(info, **kwargs)