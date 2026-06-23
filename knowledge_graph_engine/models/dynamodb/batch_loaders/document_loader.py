# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, List, Tuple

from promise import Promise

from ..document import DocumentModel
from .base import SafeDataLoader, normalize_model, Key


class DocumentLoader(SafeDataLoader):
    """Loads documents by (partition_key, document_uuid) tuples."""

    def __init__(self, logger=None, cache_enabled=True, **kwargs):
        super(DocumentLoader, self).__init__(
            logger=logger, cache_enabled=cache_enabled, **kwargs
        )

    def batch_load_fn(self, keys: List[Key]) -> Promise:
        results = []
        for partition_key, document_uuid in keys:
            try:
                doc = DocumentModel.get(partition_key, document_uuid)
                results.append(normalize_model(doc))
            except DocumentModel.DoesNotExist:
                results.append(None)
        return Promise.resolve(results)