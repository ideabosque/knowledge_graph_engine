# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from promise import Promise

from ..document import DocumentModel
from .base import SafeDataLoader


class DocumentLoader(SafeDataLoader):
    """Loads documents by (partition_key, document_uuid) tuples."""

    def batch_load_fn(self, keys):
        results = []
        for partition_key, document_uuid in keys:
            try:
                doc = DocumentModel.get(partition_key, document_uuid)
                from ...utils.normalization import normalize_to_json
                results.append(normalize_to_json(doc))
            except DocumentModel.DoesNotExist:
                results.append(None)
        return Promise.resolve(results)