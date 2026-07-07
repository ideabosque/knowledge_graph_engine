# -*- coding: utf-8 -*-
"""PostgreSQL SQLAlchemy base metadata and shared helpers.

This module is only imported when ``DB_BACKEND=postgresql``.
DynamoDB-only installs never import SQLAlchemy.

Table name prefix
-----------------
``Base.table_prefix`` is set by ``Config._initialize_db_session`` from the
``pg_table_prefix`` setting (e.g. ``"kge_"``).  All models use
``declared_attr`` for ``__tablename__`` so the prefix is applied when the
class is defined.  Models must be imported **after** ``Base.table_prefix``
is configured — the ``_import_all_models`` flow in ``utils.py`` guarantees
this because ``Config.initialize`` runs before table creation.
"""
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import declarative_base, declared_attr
    from sqlalchemy.orm import scoped_session, sessionmaker
except ImportError:  # pragma: no cover - DynamoDB-only environments
    raise ImportError(
        "SQLAlchemy is required for PostgreSQL backend. "
        "Install with: pip install knowledge-graph-engine[postgresql]"
    )

Base = declarative_base()
# Configured by Config._initialize_db_session before models are imported.
Base.table_prefix = ""  # type: ignore[attr-defined]


def prefixed_table(name: str) -> str:
    """Return ``name`` with the configured table prefix prepended."""
    return f"{Base.table_prefix}{name}"


def prefixed_index(name: str) -> str:
    """Return an index name with the configured table prefix prepended."""
    return f"{Base.table_prefix}{name}"


def normalize_row(row: Any) -> Optional[Dict[str, Any]]:
    """Convert a SQLAlchemy model instance to a normalized dict.

    Handles UUID, datetime, JSONB, and Decimal types for JSON serialization.
    Unlike the DynamoDB normalize_to_json (which wraps lists/dicts in
    {"value": ...} for PynamoDB compatibility), this returns raw values
    for JSONB columns.
    """
    if row is None:
        return None

    if isinstance(row, dict):
        # Already a dict — serialize values but don't wrap lists/dicts
        return {k: _serialize_value(v) for k, v in row.items()}

    # SQLAlchemy ORM object — extract column attributes
    if hasattr(row, "__table__"):
        result = {}
        for col in row.__table__.columns:
            key = col.name
            val = getattr(row, key, None)
            result[key] = _serialize_value(val)
        return result

    return row


def _serialize_value(val: Any) -> Any:
    """Serialize individual SQLAlchemy column values to JSON-safe types."""
    import datetime
    from decimal import Decimal
    from uuid import UUID as UUIDType

    if val is None:
        return None
    if isinstance(val, UUIDType):
        return str(val)
    if isinstance(val, (datetime.datetime, datetime.date)):
        # Return the datetime object directly — graphene's DateTime scalar
        # calls .isoformat() itself.  Returning a string here causes
        # "DateTime cannot represent value" because graphene's serialize()
        # requires a datetime.datetime / datetime.date instance, not a str.
        return val
    if isinstance(val, Decimal):
        # Preserve numeric exactness as float for JSON; the GraphQL
        # boundary handles SafeFloat conversion.
        return float(val)
    if isinstance(val, (list, dict)):
        return val
    return val


__all__ = ["Base", "normalize_row"]