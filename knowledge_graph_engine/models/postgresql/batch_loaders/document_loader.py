# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for Document entity."""
from __future__ import print_function

__author__ = "silvaengine"

from promise import Promise

from ....handlers.config import Config
from ...postgresql.base import normalize_row
from ...postgresql.document import DocumentModel
from .base import SafeDataLoader


class PGDocumentLoader(SafeDataLoader):
    """Loads documents by (partition_key, document_uuid) tuples from PostgreSQL."""

    def batch_load_fn(self, keys):
        session = Config.db_session
        results = []
        for partition_key, document_uuid in keys:
            try:
                row = (
                    session.query(DocumentModel)
                    .filter(
                        DocumentModel.partition_key == partition_key,
                        DocumentModel.document_uuid == document_uuid,
                    )
                    .first()
                )
                results.append(normalize_row(row) if row else None)
            except Exception:
                if self.logger:
                    self.logger.warning(
                        f"PGDocumentLoader: Failed to load document {partition_key}/{document_uuid}"
                    )
                results.append(None)
        return Promise.resolve(results)


__all__ = ["PGDocumentLoader"]