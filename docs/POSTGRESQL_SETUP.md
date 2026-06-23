# PostgreSQL Setup Guide

> This guide covers setting up PostgreSQL as the metadata backend for the
> Knowledge Graph Engine. Neo4j is still required for the knowledge graph
> store — see the main README for Neo4j setup.

## Prerequisites

1. **PostgreSQL 12+** running and accessible
2. **Python 3.8+** with pip
3. **Neo4j 5+** (required regardless of metadata backend)

## Step 1: Install with PostgreSQL extra

```bash
cd knowledge_graph_engine
pip install -e ".[postgresql]"
```

This installs `SQLAlchemy>=1.4`, `psycopg2-binary>=2.9`, and `alembic>=1.10`
in addition to the core dependencies. DynamoDB-only installs do not pull
these packages.

## Step 2: Create the database

```sql
-- Connect as superuser
CREATE USER silvaengine WITH PASSWORD 'silvaengine';
CREATE DATABASE silvaengine OWNER silvaengine;
GRANT ALL PRIVILEGES ON DATABASE silvaengine TO silvaengine;

-- The uuid-ossp extension is not required for KGE because it uses
-- string-based UUIDs (e.g. "doc-...", "req-..."), not native UUID columns.
```

## Step 3: Configure environment

In your `.env` or settings dict:

```env
# Switch backend
db_backend=postgresql

# PostgreSQL connection (matches Config._initialize_db_session)
PG_HOST=localhost
PG_PORT=5432
PG_USER=silvaengine
PG_PASSWORD=silvaengine
PG_DB=silvaengine

# Or use a single DATABASE_URL (overrides PG_* keys)
# DATABASE_URL=postgresql+psycopg2://silvaengine:silvaengine@localhost:5432/silvaengine

# Auto-create tables on startup (optional — you can use Alembic instead)
initialize_tables=1

# AWS credentials are still needed for Lambda dispatch and S3 file parsing
region_name=us-east-1
aws_access_key_id=...
aws_secret_access_key=...

# Neo4j is always required
neo4j_uri=bolt://localhost:7687
neo4j_username=neo4j
neo4j_password=...
```

## Step 4: Create tables

### Option A: Auto-create (simplest)

Set `initialize_tables=1` in your settings. On startup, `Config.initialize()`
calls `models/postgresql/utils.py:initialize_tables()` which runs
`Base.metadata.create_all(checkfirst=True)`. This creates all 5 tables
if they don't exist.

### Option B: Alembic migrations (recommended for production)

```bash
# Set DATABASE_URL or ensure Config can resolve PG connection
export DATABASE_URL=postgresql+psycopg2://silvaengine:silvaengine@localhost:5432/silvaengine

# Run all migrations
alembic -c migration/alembic.ini upgrade head

# Check current revision
alembic -c migration/alembic.ini current
```

Migrations create the 5 tables with proper indexes, including partial unique
indexes for the single-active invariant on `graph_schemas` and
`neo4j_instances`:

```sql
CREATE UNIQUE INDEX idx_graph_schemas_one_active
  ON graph_schemas (partition_key) WHERE status = 'active';

CREATE UNIQUE INDEX idx_neo4j_instances_one_active
  ON neo4j_instances (partition_key) WHERE status = 'active';
```

## Step 5: Verify

```bash
# Run the dual-backend tests (no live DB needed)
pytest tests/test_backend_agnostic_dispatch.py tests/test_business_flow_parity.py -v

# Run with a live PostgreSQL (set DATABASE_URL or PG_* env vars first)
pytest tests/test_integration.py -v
```

## Table Schema Overview

| Table | Primary Key | Notable Columns | Indexes |
| --- | --- | --- | --- |
| `documents` | `(partition_key, document_uuid)` | `content TEXT`, `content_embedding JSONB` | `(partition_key, updated_at)`, `(partition_key, document_external_id)`, `(partition_key, status)` |
| `graph_schemas` | `(partition_key, schema_name)` | `schema_definition JSONB`, `text2cypher_examples JSONB` | `(partition_key, updated_at)`, `(partition_key, status)`, partial unique `WHERE status = 'active'` |
| `neo4j_instances` | `(partition_key, instance_id)` | `neo4j_uri`, `neo4j_password` | `(partition_key, status)`, partial unique `WHERE status = 'active'` |
| `requests` | `(partition_key, request_uuid)` | `results JSONB`, `search_mode` | `(partition_key, search_mode)` |
| `document_process_errors` | `(partition_key, process_error_uuid)` | `error_message TEXT` | none |

All timestamp columns use `TIMESTAMP(timezone=True)` with
`server_default = NOW()`.

## Switching Back to DynamoDB

Set `db_backend=dynamodb` (or remove the `db_backend` key entirely — DynamoDB
is the default). No code changes needed — the repository dispatch boundary
handles the switch automatically.

## Troubleshooting

### `ImportError: SQLAlchemy is required for PostgreSQL backend`

You haven't installed the `[postgresql]` extra:
```bash
pip install -e ".[postgresql]"
```

### `KeyError: No repository registered for entity '...' on backend 'postgresql'`

A PostgreSQL repository file failed to import. Check that all PG model
modules compile and that SQLAlchemy is installed. The `register_all`
function in `models/repositories/postgresql/__init__.py` uses `importlib`
with `try/except ImportError` — a broken model module will silently skip
registration.

### `sqlalchemy.exc.OperationalError: could not connect to server`

Verify your `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`, `PG_DB` values
or `DATABASE_URL`. Ensure PostgreSQL is running and accepting connections
on the specified host/port.