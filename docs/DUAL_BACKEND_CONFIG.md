# Dual-Backend Configuration

> The Knowledge Graph Engine supports two selectable persistence backends for
> its five metadata entities (Document, GraphSchema, Neo4jInstance, Request,
> DocumentProcessError). **Neo4j is the knowledge-graph store and is required
> under both backends** — it is not part of the backend selection.

## Backend Selection

Set `db_backend` in your settings dict (or `DB_BACKEND` / `db_backend` env var):

| Value | Behavior |
| --- | --- |
| `dynamodb` (default) | PynamoDB models under `models/dynamodb/`, DynamoDB table initialization, `@method_cache` enabled |
| `postgresql` | SQLAlchemy models under `models/postgresql/`, Alembic migrations, `Config.db_session` scoped session, no `@method_cache` |

Invalid values raise `ValueError` at `Config.initialize()`.

## How It Works

A repository dispatch boundary at `models/repositories/` isolates all GraphQL
queries, mutations, and domain handlers from backend-specific persistence:

```text
GraphQL layer (queries/, mutations/, schema.py)
    │  routes through get_repo(entity_type) / get_loaders(context)
    ▼
models/repositories/dispatch.py
    ├── DynamoDB: models/dynamodb/ + repositories/dynamodb/ (thin wrappers)
    └── PostgreSQL: models/postgresql/ + repositories/postgresql/ (SQLAlchemy)
```

`get_repo("document")` returns the active backend's repository. The GraphQL
layer never imports `models.dynamodb` or `models.postgresql` directly — a
static adoption guard test enforces this.

## DynamoDB Mode (default)

No extra dependencies required. PynamoDB models use `@method_cache` from
`silvaengine_utility` for getter caching. Table creation is handled by
`models/dynamodb/utils.py:initialize_tables()` when `initialize_tables=1`.

Settings:
```python
settings = {
    "db_backend": "dynamodb",        # default, can be omitted
    "region_name": "us-east-1",
    "aws_access_key_id": "...",
    "aws_secret_access_key": "...",
    "initialize_tables": 1,          # auto-create DynamoDB tables
}
```

## PostgreSQL Mode

Requires the `[postgresql]` extra:
```bash
pip install -e ".[postgresql]"
```

Settings:
```python
settings = {
    "db_backend": "postgresql",
    "db_host": "localhost",
    "db_port": "5432",
    "db_user": "silvaengine",
    "db_password": "silvaengine",
    "db_schema": "silvaengine",
    "initialize_tables": 1,          # auto-create PG tables via Base.metadata.create_all
    # AWS credentials are still used for Lambda dispatch and S3 file parsing
    "region_name": "us-east-1",
    "aws_access_key_id": "...",
    "aws_secret_access_key": "...",
}
```

AWS services (`aws_lambda`, S3) remain initialized even in PostgreSQL mode
because KGE uses Lambda for dispatch and S3 for file parsing. This differs
from `rfq_engine` where AWS is optional in PG mode.

## Cache Configuration

Cache config is backend-aware:

- **DynamoDB**: `CACHE_ENTITY_CONFIG_DYNAMODB` is populated for all 5 entities
  with `@method_cache` decorators. `CACHE_RELATIONSHIPS_DYNAMODB` defines
  cascading invalidation paths.
- **PostgreSQL**: `CACHE_ENTITY_CONFIG_POSTGRESQL` is empty — PG repositories
  do not use `@method_cache`. Request-scoped DataLoader caching is still
  active via `PGRequestLoaders`.

`Config.get_cache_entity_config()` and `Config.get_cache_relationships()`
return the active backend's config automatically.

## Single-Active Invariant

`graph_schema` and `neo4j_instance` enforce "at most one `active` record per
partition":

- **DynamoDB**: Enforced in application code (`_deactivate_current_active_schema`
  / `_deactivate_current_active_instance` called before activating a new one).
- **PostgreSQL**: Enforced in application code **and** at the database level
  via a partial unique index: `CREATE UNIQUE INDEX ... ON table(partition_key)
  WHERE status = 'active'`. This prevents race conditions from creating
  multiple active records.

## Driver-Cache Invalidation

When a `neo4j_instance` is mutated or deleted, the cached Neo4j driver must
be invalidated so the next request picks up the new active instance. This
hook lives above the repository boundary and fires on both backends:

```python
Neo4jConnectionManager.close_driver(partition_key)
Config.clear_graph_rag_util(partition_key)
```

## DataLoader Dispatch

`get_loaders(context)` returns request-scoped loaders for the active backend:

- **DynamoDB**: `RequestLoaders` — eagerly instantiates `DocumentLoader`,
  `GraphSchemaLoader`. Memoized on `context["batch_loaders"]`.
- **PostgreSQL**: `PGRequestLoaders` — lazily instantiates `PGDocumentLoader`,
  `PGGraphSchemaLoader` via `importlib`. Same memoization key.

## Alembic Migrations (PostgreSQL only)

```bash
# Set DATABASE_URL or use Config settings
alembic -c migration/alembic.ini upgrade head

# Generate a new migration after model changes
alembic -c migration/alembic.ini revision --autogenerate -m "description"
```

Migration files are in `migration/alembic/versions/`:
- `0001_create_documents.py`
- `0002_create_graph_schemas.py` (includes partial unique index)
- `0003_create_neo4j_instances.py` (includes partial unique index)
- `0004_create_requests.py`
- `0005_create_document_process_errors.py`

URL resolution order: `DATABASE_URL` env var → `Config.get_setting()` (if
initialized with PG backend) → `alembic.ini` fallback.