# -*- coding: utf-8 -*-
"""PostgreSQL table initialization and shared utilities.

Only imported when DB_BACKEND=postgresql.
"""
from __future__ import print_function

__author__ = "silvaengine"

import logging
from typing import Any

from .base import Base


def initialize_tables(logger: logging.Logger, db_session: Any) -> None:
    """Create all PostgreSQL tables that have been imported.

    This uses SQLAlchemy metadata.create_all() which is idempotent —
    it only creates tables that don't already exist.
    """
    # Import all model modules so their SQLAlchemy classes register
    # with the Base.metadata
    _import_all_models()

    engine = db_session.get_bind()
    Base.metadata.create_all(bind=engine, checkfirst=True)
    logger.info("PostgreSQL tables initialized (create_all with checkfirst=True).")


def _import_all_models() -> None:
    """Import all PostgreSQL model modules to register them with Base.metadata."""
    model_modules = [
        ".document",
        ".graph_schema",
        ".neo4j_instance",
        ".request",
        ".document_process_error",
    ]
    for mod_name in model_modules:
        try:
            __import__(
                f"knowledge_graph_engine.models.postgresql{mod_name}",
                fromlist=["x"],
            )
        except ImportError:
            # Model not yet ported — skip silently
            _logger = logging.getLogger(__name__)
            _logger.debug(f"PostgreSQL model not yet available: {mod_name}")


__all__ = ["initialize_tables"]