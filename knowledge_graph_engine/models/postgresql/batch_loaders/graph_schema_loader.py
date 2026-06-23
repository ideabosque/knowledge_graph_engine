# -*- coding: utf-8 -*-
"""PostgreSQL batch loader for GraphSchema entity."""
from __future__ import print_function

__author__ = "silvaengine"

from promise import Promise

from ....handlers.config import Config
from ...postgresql.base import normalize_row
from ...postgresql.graph_schema import GraphSchemaModel
from .base import SafeDataLoader


class PGGraphSchemaLoader(SafeDataLoader):
    """Loads graph schemas by (partition_key, schema_name) tuples from PostgreSQL."""

    def batch_load_fn(self, keys):
        session = Config.db_session
        results = []
        for partition_key, schema_name in keys:
            try:
                row = (
                    session.query(GraphSchemaModel)
                    .filter(
                        GraphSchemaModel.partition_key == partition_key,
                        GraphSchemaModel.schema_name == schema_name,
                    )
                    .first()
                )
                results.append(normalize_row(row) if row else None)
            except Exception:
                if self.logger:
                    self.logger.warning(
                        f"PGGraphSchemaLoader: Failed to load schema {partition_key}/{schema_name}"
                    )
                results.append(None)
        return Promise.resolve(results)


__all__ = ["PGGraphSchemaLoader"]