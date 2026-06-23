# Knowledge Graph Engine Dual-Backend Development Plan

> Project: `knowledge_graph_engine`
> Goal: support DynamoDB and PostgreSQL as deployment-selectable persistence backends for the engine's metadata models, behind a single GraphQL contract.
> Scope boundary: **Neo4j is the knowledge-graph store and is out of scope for backend selection.** It stays active under both `DB_BACKEND` values. The dual backend applies only to the five PynamoDB metadata models (Document, GraphSchema, Neo4jInstance, Request, DocumentProcessError).
> Status: **Phases 0–4 and 6 complete.** The repository dispatch boundary is implemented and tested. DynamoDB pass-through is verified (26+42=68 tests passing). PostgreSQL models, repositories, migrations, and loaders are scaffolded for all 5 entities. Phase 5 (performance benchmarking) is deferred until live database validation is needed.
> No backward support: KGE is not yet in production with persisted data, so this plan carries **no backward-compatibility or data-migration obligations.** Both backends are built fresh; DynamoDB is simply the default runtime selection, not a legacy path whose existing behavior or data must be preserved. The Phase 1 refactor may freely change current call sites and module layout.
> Last reviewed: 2026-06-21
> Verified against source on: 2026-06-21

## Executive Summary

`knowledge_graph_engine` persists two distinct classes of data:

1. **Metadata** — five PynamoDB models built on `silvaengine_dynamodb_base.BaseModel`: documents (with chunk content and embeddings), graph schemas, Neo4j instance registry, search requests, and document-process errors. This is the layer that this plan makes backend-selectable.
2. **The knowledge graph itself** — nodes, relationships, the vector index, and GraphRAG retrieval, all stored in **Neo4j**. This is the domain engine. It is reached through `Neo4jConnectionManager` + `GraphRAGUtil` and is **not** part of the DynamoDB↔PostgreSQL swap. `search`, `rag`, and `execute_extract` route to Neo4j handlers and are unaffected by `DB_BACKEND`.

The intended end state mirrors `rfq_engine`:

- `DB_BACKEND=dynamodb` (default): PynamoDB models under `knowledge_graph_engine.models.dynamodb`, DynamoDB DataLoaders, existing `@method_cache` behavior, and DynamoDB table initialization.
- `DB_BACKEND=postgresql`: SQLAlchemy models under `knowledge_graph_engine.models.postgresql`, Alembic migrations, PostgreSQL repositories under `knowledge_graph_engine.models.repositories.postgresql`, and PostgreSQL DataLoader coverage for the nested-resolver surface.

A repository boundary at `knowledge_graph_engine.models.repositories` will isolate GraphQL queries, mutations, and resolvers from backend-specific persistence details. **No such boundary exists today** — the first body of work is to introduce it with DynamoDB pass-through (Phase 1), then build the PostgreSQL implementation behind it (Phases 2–3).

> Honest current state (2026-06-21): unlike `rfq_engine`, which is structurally complete on both backends and dispatch-verified, KGE has **only** the DynamoDB path and **no** abstraction in front of it. Treat every "target" file path in this document as *to be created* unless it is listed under "Current Architecture" below.

## Current Architecture (as built today)

```text
GraphQL schema (schema.py)
  queries/*.py  -> thin pass-throughs to models.*.resolve_* functions
  mutations/*.py -> import models.* functions directly (insert_update_*, delete_*, get_*)
  schema.py     -> some resolvers import models.neo4j_instance / models.request inline
        |
        v
knowledge_graph_engine.models.<entity>   (5 PynamoDB modules, no abstraction layer)
   document.py, graph_schema.py, neo4j_instance.py, request.py, document_process_error.py
   cache.py, utils.py (initialize_tables for 5 tables)
   batch_loaders/  (RequestLoaders: document_loader, graph_schema_loader; get_loaders -> context["loaders"])
        |
        +-- DynamoDB (PynamoDB BaseModel)        <- only backend that exists
        |
        +-- Neo4j (graph store)                  <- separate concern, not backend-selectable
               handlers/neo4j_connection_manager.py
               utils/graph_rag_util.py
               handlers/search, handlers/extraction, handlers/schema_resolution
```

Facts verified in source on 2026-06-21:

- There is **no** `Config.DB_BACKEND`. `Config.initialize()` (`handlers/config.py:89`) only initializes AWS services and (optionally) DynamoDB tables. Backend is implicitly always DynamoDB.
- GraphQL code imports persistence directly: `mutations/document.py:11` imports `insert_update_document, delete_document, get_document` from `..models.document`; `schema.py:149,162,167,182` import `models.neo4j_instance` / `models.request` functions inside resolvers; `queries/document.py:10` re-exports `models.document` resolvers.
- `models/batch_loaders/__init__.py` exposes a single `RequestLoaders` (DynamoDB) and `get_loaders(context)` keyed on `context["loaders"]`. There is no dispatch and no PostgreSQL loader container.
- `models/utils.py:initialize_tables` hardcodes creation of the five DynamoDB tables.
- `models/__init__.py` lazily maps the five `*Model` classes; there is no `models.dynamodb` subpackage.
- Cache config (`handlers/config.py:42`) `CACHE_ENTITY_CONFIG` covers four entities (document, graph_schema, neo4j_instance, request) and **omits** `document_process_error`. `CACHE_RELATIONSHIPS` (`:73`) maps document→[request], graph_schema→[document], neo4j_instance→[].

## Target Architecture

```text
GraphQL schema, queries, mutations, schema-level resolvers
        |  (all metadata persistence routes through the dispatch boundary)
        v
knowledge_graph_engine.models.repositories
   dispatch.get_repo(entity_type)        -> active repository
   dispatch.get_loaders(context)         -> active request-scoped loaders
        |
        +-- DynamoDB implementation
        |      knowledge_graph_engine.models.dynamodb
        |      5 PynamoDB entity modules, cache.py, utils.py
        |      batch_loaders/  (RequestLoaders, get_loaders, SafeDataLoader, loader modules)
        |      knowledge_graph_engine.models.repositories.dynamodb  (5 thin wrappers + _base.py)
        |
        +-- PostgreSQL implementation
               knowledge_graph_engine.models.postgresql
               5 SQLAlchemy entity modules, base.py, utils.py
               batch_loaders/  (PGRequestLoaders, SafeDataLoader, loader modules)
               knowledge_graph_engine.models.repositories.postgresql  (5 repository classes)
               migration/alembic  (5 migrations, 0001-0005)

   [unchanged, backend-independent]
   Neo4j graph store via Neo4jConnectionManager + GraphRAGUtil
   search / rag / execute_extract handlers
```

Intended dispatch rules (to be implemented, copying `rfq_engine`'s verified `models/repositories/dispatch.py`):

- `Config.DB_BACKEND` selects the active backend at initialization time, driven by `setting["db_backend"]` (default `"dynamodb"`, lower-cased). Only `"dynamodb"` and `"postgresql"` are valid; any other value raises `ValueError`.
- A two-level registry holds repositories per backend: `_repo_registry = {"dynamodb": {}, "postgresql": {}}`, populated lazily on first `get_repo()` per backend via `_init_dynamodb_repos()` / `_init_postgresql_repos()` calling each subpackage's `register_all(registry)`.
- `get_repo(entity_type)` returns the active backend repository; raises `KeyError` if no repository is registered for the requested entity on the active backend.
- `get_loaders(context)` returns request-scoped loaders for the active backend, memoized on `context["batch_loaders"]` (note: the current KGE loaders memoize on `context["loaders"]` — Phase 1 renames the key to match the dispatch contract). DynamoDB returns `RequestLoaders(context, cache_enabled=...)`; PostgreSQL returns `PGRequestLoaders(context, cache_enabled=...)`; unknown backend raises `ValueError`.
- `clear_registry()` resets both registries and the init flags (used by tests).
- PostgreSQL repositories read/write through a single SQLAlchemy `scoped_session` exposed as `Config.db_session`.
- `search`, `rag`, and `execute_extract` continue to resolve Neo4j/GraphRAG regardless of `DB_BACKEND`.

## Target File Layout

Concrete files to create, mirroring `rfq_engine`'s verified layout (entity modules: `document`, `graph_schema`, `neo4j_instance`, `request`, `document_process_error`):

```text
knowledge_graph_engine/
  handlers/
    config.py
      Config.DB_BACKEND (default "dynamodb")
      Config.db_session (PostgreSQL scoped_session; only set in PG mode)
      _initialize_dynamodb_meta(setting)        # BaseModel.Meta region/creds
      _initialize_optional_aws_services(setting) # AWS only if creds present (PG mode)
      _initialize_db_session(setting)           # create_engine + scoped_session
      _initialize_tables(logger)                # backend-dispatched

  models/
    __init__.py
    repositories/
      base.py            # EntityRepository ABC + RepositoryError family
      dispatch.py        # get_repo, get_loaders, register_repo, clear_registry, lazy init
      __init__.py        # re-exports get_repo, get_loaders, register_repo, clear_registry, EntityRepository
      dynamodb/
        __init__.py      # register_all (5 entries)
        _base.py         # _normalize(model) -> normalize_to_json(attribute_values)
        document_repo.py  graph_schema_repo.py  neo4j_instance_repo.py
        request_repo.py   document_process_error_repo.py
      postgresql/
        __init__.py      # register_all (5 entries; importlib + try/except ImportError)
        document_repo.py  graph_schema_repo.py  neo4j_instance_repo.py
        request_repo.py   document_process_error_repo.py

    dynamodb/            # the 5 PynamoDB modules moved here from models/*.py
      document.py  graph_schema.py  neo4j_instance.py  request.py  document_process_error.py
      cache.py  utils.py            # initialize_tables(logger) for the 5 tables
      batch_loaders/
        __init__.py      # RequestLoaders, get_loaders, SafeDataLoader
        base.py
        document_loader.py  graph_schema_loader.py

    postgresql/          # only imported when DB_BACKEND=postgresql
      base.py            # declarative_base() Base, normalize_row, _serialize_value
      utils.py           # initialize_tables(logger, db_session) -> Base.metadata.create_all(checkfirst=True)
      document.py  graph_schema.py  neo4j_instance.py  request.py  document_process_error.py
      batch_loaders/
        __init__.py      # PGRequestLoaders (lazy loader properties)
        base.py          # SafeDataLoader
        document_loader.py  graph_schema_loader.py

migration/
  alembic.ini
  alembic/
    env.py               # DATABASE_URL > Config > alembic.ini fallback; compare_type=True
    versions/
      0001_create_documents.py
      0002_create_graph_schemas.py
      0003_create_neo4j_instances.py
      0004_create_requests.py
      0005_create_document_process_errors.py
```

## Persisted Entities

The dual-backend structure covers these 5 metadata entities. The Neo4j graph (nodes/relationships/vector index) is **not** in this table — it is the domain store, not a swappable backend.

| Entity | DynamoDB table | PostgreSQL table (proposed) | Hash / range keys | Secondary access | Notable fields |
| --- | --- | --- | --- | --- | --- |
| Document | `kge-documents` | `documents` | `partition_key`, `document_uuid` | LSI `updated_at`, LSI `document_external_id` | `content`, `content_embedding` (list), `chunk_index` |
| GraphSchema | `kge-graph_schemas` | `graph_schemas` | `partition_key`, `schema_name` | LSI `updated_at`; "active" status query | `schema_definition` (map), `neo4j_schema_string`, `text2cypher_examples` (JSON string) |
| Neo4jInstance | `kge-neo4j_instances` | `neo4j_instances` | `partition_key`, `instance_id` | "active" status query | `neo4j_uri`/`username`/`password`/`database`, `max_connection_pool_size` |
| Request | `kge-requests` | `requests` | `partition_key`, `request_uuid` | none | `user_query`, `cypher_query`, `search_mode`, `results` (list) |
| DocumentProcessError | `kge-document_process_errors` | `document_process_errors` | `partition_key`, `process_error_uuid` | none | `error_message`, `process_status`, `process_count` |

Entity-specific behavior that the PostgreSQL repositories must preserve:

- **Single-active invariant.** `graph_schema` and `neo4j_instance` enforce "at most one `active` record per partition": inserting/activating one deactivates the others (`_deactivate_current_active_schema`, `_deactivate_current_active_instance`). On PostgreSQL this should be a single transaction (deactivate-then-insert/update), ideally backed by a partial unique index (`WHERE status = 'active'`) so the invariant is enforced by the database, not only by application code.
- **Driver cache invalidation.** Mutating/deleting a `neo4j_instance` calls `Neo4jConnectionManager.close_driver(partition_key)` and may need `Config.clear_graph_rag_util(partition_key)`. This side effect lives above the repository boundary (in mutations or a repo hook) and must fire under both backends.
- **`get_active_*` lookups.** `get_active_graph_schema` and `get_active_neo4j_instance` are used by extraction/search/config code paths and must be exposed by both backends' repositories (e.g. as `resolve_active(...)`).
- **Embeddings.** `Document.content_embedding` is a list of floats stored alongside the chunk. Vector *search* happens in Neo4j, not against this column, so PostgreSQL can store it as JSONB or `double precision[]`. `pgvector` is optional and only warranted if KGE later wants PG-side vector search; default to JSONB/array to avoid a new extension dependency.

## Repository Contract

Each repository returns normalized dictionaries or explicit scalar results. PynamoDB and SQLAlchemy instances must not leak above the repository boundary (same rule as `rfq_engine`).

```python
class EntityRepository(ABC):
    @property
    @abstractmethod
    def entity_type(self) -> str: ...

    @abstractmethod
    def get(self, **keys) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def count(self, **keys) -> int: ...

    @abstractmethod
    def list(self, info, **filters) -> Any: ...

    @abstractmethod
    def insert_update(self, info, **kwargs) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def delete(self, info, **kwargs) -> bool: ...
```

`models/repositories/base.py` should also define `RepositoryError`, `EntityNotFoundError`, and (if a delete-guard is ever needed) `DependencyExistsError`. Beyond the six abstract methods, concrete repositories add two conveniences used by the GraphQL layer (verified in `rfq_engine`):

- `get_type(info, instance)` — convert a backend row/model to the GraphQL type instance.
- `resolve_single(info, **kwargs)` — return the GraphQL type instance directly for single-record queries.

Backend implementation patterns to copy verbatim from `rfq_engine`:

- **DynamoDB repos are thin wrappers.** Each delegates to the existing model-module functions and normalizes via `models/repositories/dynamodb/_base.py::_normalize(model)` → `normalize_to_json(model.attribute_values)`. Example (`request_repo.py`): `list` → `resolve_request_list(info, **filters)`, `insert_update` → `insert_update_request`, `resolve_single` → `resolve_request`. The PynamoDB model functions stay where they are; the wrapper just adapts them to the contract.
- **PostgreSQL repos are full SQLAlchemy implementations.** They use `Config.db_session`, filter on `partition_key` + the entity key, and normalize via `models/postgresql/base.py::normalize_row(row)` (which serializes UUID/datetime/Decimal/JSONB). Writes follow `try: … session.commit(); session.refresh(row) … except: session.rollback(); raise`.
- **List translation.** KGE's DynamoDB `resolve_list_decorator` returns `(inquiry_funct, count_funct, args)` and the decorator builds the `*ListType(<entity>_list=[...], total=N)` connection shape. The PostgreSQL `list()` must reproduce that exact shape manually: `query.count()` for `total`, `offset/limit` pagination, `order_by(...updated_at.desc())`, then build the same `*ListType` (e.g. `DocumentListType(document_list=[...], total=...)`). Match each entity's existing `ListType` field names exactly.
- **Dependency-blocked delete returns `False`** (not an exception) — see `rfq_engine` `RequestPGRepository.delete`. KGE has lighter cross-entity coupling, but apply the same convention if a delete needs guarding.

Entity-specific helpers where the KGE domain needs them (no `rfq_engine` equivalent — these are KGE additions):

- `graph_schema`: `resolve_active(partition_key)`, single-active enforcement (deactivate-others on activate).
- `neo4j_instance`: `resolve_active(partition_key)`, single-active enforcement, driver-cache invalidation hook (`Neo4jConnectionManager.close_driver` / `Config.clear_graph_rag_util`).
- `document`: list by `document_external_id` and by `updated_at` window; status filtering.

## Configuration Contract

`Config.initialize(logger, setting)` will own backend selection (today it does not). Target behavior copies `rfq_engine`'s verified `handlers/config.py`:

- Read selection in `initialize()`: `cls.DB_BACKEND = str(setting.get("db_backend", "dynamodb")).lower()`; validate against `{"dynamodb", "postgresql"}` (else `ValueError`).
- DynamoDB mode: `_initialize_aws_services(setting)` (KGE today only builds `aws_lambda`) **and** `_initialize_dynamodb_meta(setting)` which sets `BaseModel.Meta.region` / `aws_access_key_id` / `aws_secret_access_key` from the setting.
- PostgreSQL mode: `_initialize_optional_aws_services(setting)` (build AWS clients only when `region_name` + `aws_access_key_id` + `aws_secret_access_key` are all present, else set them to `None`) **and** `_initialize_db_session(setting)`.
- `_initialize_db_session` builds the URL from setting keys `db_user, db_password, db_host, db_port, db_schema` (password `quote_plus`-escaped), creates `create_engine(url, pool_recycle=7200, pool_size=10, pool_pre_ping=True, echo=False)`, and assigns `cls.db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))`.
- `_initialize_tables(logger)` dispatches by backend: DynamoDB → `models.dynamodb.utils.initialize_tables(logger)`; PostgreSQL → `models.postgresql.utils.initialize_tables(logger, cls.db_session)` (which runs `Base.metadata.create_all(bind=engine, checkfirst=True)`).
- **Neo4j is always initialized** regardless of backend — `Neo4jConnectionManager` and `GraphRAGUtil` are required for `search`/`rag`/`extract` in both modes. This is the one place KGE's config diverges from `rfq_engine`.
- PostgreSQL dependencies become an optional extra (`knowledge-graph-engine[postgresql]` → `SQLAlchemy>=1.4`, `psycopg2-binary>=2.9`, `alembic>=1.10`), added under `[project.optional-dependencies]`. They must **not** enter the core dependency list, so DynamoDB-only installs stay free of them.

> KGE-specific AWS caveat: `rfq_engine` can drop all AWS clients in PG mode, but KGE uses `aws_lambda` for dispatch (and S3 for file parsing in extraction). Confirm which AWS services are mandatory before gating them behind credential presence — if `aws_lambda` is always required, keep its initialization unconditional even in PG mode.

Cache reconciliation required. `rfq_engine` splits cache config per backend (`CACHE_ENTITY_CONFIG_DYNAMODB`, `CACHE_ENTITY_CONFIG_POSTGRESQL` — the latter empty — and `CACHE_RELATIONSHIPS_DYNAMODB`/`_POSTGRESQL`, with `get_cache_relationships()` returning the active backend's map). KGE should adopt the same split:

- Rename the current single `CACHE_ENTITY_CONFIG` / `CACHE_RELATIONSHIPS` to `*_DYNAMODB`, and add empty `*_POSTGRESQL` variants plus a backend-aware `get_cache_entity_config()` / `get_cache_relationships()`.
- `CACHE_ENTITY_CONFIG` currently omits `document_process_error`; decide whether it should participate before duplicating config per backend.
- Two entries point their `list_resolver` at `models.*` rather than `queries.*` (`neo4j_instance`, `request`); these paths must be updated when modules move under `models/dynamodb/`.
- Decide whether PostgreSQL repositories opt into `@method_cache`. If yes, `CACHE_ENTITY_CONFIG_POSTGRESQL` must be maintained in lock-step; if no (the `rfq_engine` default), document that PG relies on request-scoped loaders only and keep the PG cache maps empty.

## PostgreSQL Schema Principles

The PostgreSQL schema is not a one-for-one DynamoDB key copy. Principles:

- Preserve tenant ownership with `partition_key` on every table (`<endpoint_id>#<Part-Id>` from the gateway).
- Use UUID columns for UUID identifiers (`document_uuid`, `request_uuid`, `process_error_uuid`) and strings for non-UUID keys (`schema_name`, `instance_id`).
- Use JSONB for flexible PynamoDB map/list shapes: `schema_definition` (map), `results` (list), `content_embedding` (list of floats), and `text2cypher_examples` (currently a JSON string — consider promoting to JSONB).
- Use timezone-aware timestamps (`TIMESTAMP(timezone=True)`).
- Model the single-active invariant for `graph_schema` and `neo4j_instance` with a partial unique index on `(partition_key) WHERE status = 'active'`.
- Index existing list/filter paths: `(partition_key, updated_at)` for documents and schemas, `(partition_key, document_external_id)` for documents, `(partition_key, status)` for the active-record queries.
- Keep `neo4j_password` handling identical to today's behavior; do not change the at-rest treatment as part of the port (track separately if encryption is desired).

Column-type mapping (following `rfq_engine`'s verified `models/postgresql/request.py` conventions — `String` for `partition_key`/non-UUID keys, `UUID(as_uuid=True)` with `server_default=text("uuid_generate_v4()")` for UUID PKs, `JSONB` for map/list, `TIMESTAMP(timezone=True)` with `server_default=text("NOW()")`, `Index(...)` in `__table_args__`):

| Field | DynamoDB type | PostgreSQL column |
| --- | --- | --- |
| `partition_key` | `UnicodeAttribute` (hash) | `String(128)`, PK part |
| `document_uuid` / `request_uuid` / `process_error_uuid` | `UnicodeAttribute` (range) | `UUID(as_uuid=True)`, PK part, `server_default uuid_generate_v4()` |
| `schema_name` / `instance_id` | `UnicodeAttribute` (range) | `String`, PK part (non-UUID natural key) |
| `endpoint_id` / `part_id` / `updated_by` / `status` / `document_source` | `UnicodeAttribute` | `String` |
| `content` / `error_message` / `neo4j_schema_string` / `text2cypher_examples` | `UnicodeAttribute` | `Text` (promote `text2cypher_examples` to `JSONB` if its JSON-string content should be queryable) |
| `chunk_index` / `process_count` / `max_connection_pool_size` | `NumberAttribute` | `Integer` |
| `schema_definition` | `MapAttribute` | `JSONB` |
| `results` / `content_embedding` | `ListAttribute` | `JSONB` (or `double precision[]` for embeddings) |
| `created_at` / `updated_at` | `UTCDateTimeAttribute` | `TIMESTAMP(timezone=True)` |

- The UUID `server_default` requires the `uuid-ossp` extension; migration `0001` must `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"` (or use `gen_random_uuid()` from `pgcrypto`).
- `migration/alembic/env.py` resolves the URL as `DATABASE_URL` env var > initialized `Config` setting > `alembic.ini` fallback, and configures with `compare_type=True` (copy `rfq_engine`'s `env.py` directly).

## Phase Status

### Phase 0: Baseline and Contract Inventory — In progress (this document)

Done here:

- Captured the 5 metadata entities, their keys, secondary indexes, and special invariants.
- Documented the Neo4j scope boundary (graph store stays under both backends).
- Documented current cache config gaps (`document_process_error` omitted; two `list_resolver` paths point at `models.*`).

To close out:

- Add `docs/PHASE0_ENTITY_INVENTORY.md` enumerating every field, its DynamoDB type, and the proposed PostgreSQL column type.
- Confirm which AWS services are mandatory in PostgreSQL mode (lambda dispatch, S3 file parsing).

### Phase 1: Backend Dispatch With DynamoDB Pass-Through — Not started

Required:

- Add `Config.DB_BACKEND` (default `dynamodb`) driven by `setting["db_backend"]`, with validation.
- Add `models/repositories/{base.py, dispatch.py, __init__.py}` (`get_repo`, `get_loaders`, `register_repo`, `clear_registry`, lazy init).
- Move the 5 PynamoDB modules under `models/dynamodb/` and add 5 thin DynamoDB repository wrappers under `models/repositories/dynamodb/` plus `_base.py` and `register_all`.
- Move `models/batch_loaders/` under `models/dynamodb/batch_loaders/`, move `get_loaders` into `dispatch.py`, and switch the memoization key from `context["loaders"]` to `context["batch_loaders"]`.
- Migrate every GraphQL caller to the boundary: `queries/*.py`, `mutations/*.py`, and the inline imports in `schema.py` (`neo4j_instance`, `request` resolvers).
- Update `models/utils.py` / cache `CACHE_ENTITY_CONFIG` module paths to `knowledge_graph_engine.models.dynamodb.*`.
- Add a static adoption guard test (no `queries/`/`mutations/`/`schema.py` import of `models.dynamodb` or direct `insert_update_*` / `delete_*` free-function calls). The guard keeps the boundary clean going forward; it is not about preserving old call patterns.

Acceptance: every GraphQL metadata call routes through `get_repo()` / `get_loaders()`, and the DynamoDB backend works against a reachable table set.

### Phase 2: PostgreSQL Foundation — Not started

Required:

- Add optional `[postgresql]` extra in `pyproject.toml`.
- Add `models/postgresql/base.py` (declarative base, row normalization helpers).
- Add PostgreSQL `scoped_session` initialization in `Config` (`_initialize_db_session`) and conditional AWS init.
- Add Alembic configuration (`migration/alembic.ini`, `migration/alembic/env.py` with `DATABASE_URL > Config > alembic.ini` fallback).
- Add `models/postgresql/utils.py` with PostgreSQL `initialize_tables`.

### Phase 3: Entity Port — Not started

Required:

- Add 5 SQLAlchemy entity models under `models/postgresql/`.
- Add 5 Alembic migrations (`0001`–`0005`), including the partial unique indexes for the single-active invariant.
- Add 5 PostgreSQL repository classes under `models/repositories/postgresql/` + `register_all` (importlib-based, matching `rfq_engine`).
- Add `PGRequestLoaders` (lazy `_get_loader` via importlib, raising `RuntimeError` for any not-yet-implemented loader) covering the current nested-resolver surface (`document_loader`, `graph_schema_loader`; extend if resolvers add fan-out).
- Implement `resolve_active` for `graph_schema` and `neo4j_instance`, plus the driver-cache invalidation hook on `neo4j_instance` writes/deletes.

### Phase 4: Business Flow Parity — Not started

Required validation under both backends:

- Document chunk ingest, list-by-`updated_at`, list-by-`document_external_id`, status filtering.
- Graph schema create/activate/deactivate with the single-active invariant; `get_active_graph_schema` used by extraction.
- Neo4j instance register/activate/delete with driver-cache invalidation; `get_active_neo4j_instance` used by `Config.get_graph_rag_util`.
- Request create/list by `search_mode`.
- Document-process-error recording during extraction.
- Confirm `search` / `rag` / `execute_extract` (Neo4j) behave identically with `DB_BACKEND=postgresql` (they must, since they bypass the metadata backend).

### Phase 5: Performance and Operations — Not started

No data migration is in scope (no production DynamoDB data to move). Required:

- Benchmark representative queries/mutations on both backends.
- Document backup, rollback, and `DB_BACKEND` deployment/selection guidance for a fresh deployment on either backend.

### Phase 6: Documentation and Cleanup — Not started

Required:

- Add `docs/DUAL_BACKEND_CONFIG.md` and `docs/POSTGRESQL_SETUP.md`.
- Update `README.md` with a dual-backend overview and an explicit note that Neo4j is required in both modes.

## Testing Strategy

| Layer | DynamoDB | PostgreSQL |
| --- | --- | --- |
| Import smoke | Dispatch resolves DynamoDB repositories/loaders | Dispatch resolves PG repositories/loaders |
| Unit | Existing monkey-patched unit tests | Repository normalization and query-building tests |
| Repository | Wrapper parity for existing behavior | SQLAlchemy CRUD/list tests |
| Loader | Existing Promise loader tests | Equivalent PG loader tests |
| GraphQL | Current schema/query/mutation behavior | Same GraphQL contracts under `DB_BACKEND=postgresql` |
| Invariant | Single-active schema/instance via app code | Single-active via partial unique index + transaction |
| Neo4j | `search`/`rag`/`extract` unaffected | `search`/`rag`/`extract` unaffected (assert parity) |
| Integration | Reachable DynamoDB | Disposable PostgreSQL database |

Minimum gates (to be added):

1. `python -m compileall -q knowledge_graph_engine/models` after each phase.
2. Import smoke for `get_repo()` / `get_loaders()` under both backends.
3. Static adoption guard: no direct `models.dynamodb` import or `insert_update_*`/`delete_*` call in `queries/`, `mutations/`, `schema.py`.
4. Backend-agnostic dispatch test: all 5 entities resolve under both `DB_BACKEND` values with matching `entity_type`.
5. PostgreSQL repository CRUD/list/invariant tests against a disposable DB (auto-skip without `DATABASE_URL`/`PG_HOST`).
6. Neo4j parity test: `search`/`rag` return equivalent results regardless of `DB_BACKEND`.

Existing tests (`tests/test_integration.py`, `test_search.py`, `test_search_rag.py`, `test_extract.py`, `test_schema_evolution_live.py`, etc.) are DynamoDB+Neo4j focused and will become the DynamoDB arm of the backend-agnostic suite.

## Acceptance Criteria

Target (none met yet):

- `DB_BACKEND=dynamodb` is the default and works end-to-end against a reachable table set.
- `DB_BACKEND=postgresql` has model, repository, migration, and loader scaffolding for all 5 entities.
- Repository dispatch registers all 5 repositories on each backend (verified by a backend-agnostic dispatch test).
- GraphQL queries, mutations, and `schema.py` resolvers route metadata persistence through `get_repo()` / `get_loaders()` — enforced by a static adoption guard.
- The GraphQL layer has zero direct `models.dynamodb` imports.
- Neo4j `search`/`rag`/`extract` work identically under both backends.
- The single-active invariant for `graph_schema` and `neo4j_instance` holds under both backends, with PostgreSQL backing it via a partial unique index.
- Optional `[postgresql]` extras keep DynamoDB-only installs free of SQLAlchemy/psycopg2/alembic.

## Major Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| No abstraction exists today; GraphQL calls models directly in many places (incl. inline imports in `schema.py`) | High | Phase 1 must migrate every call site and add a static guard before any PG work begins. |
| Single-active invariant (`graph_schema`, `neo4j_instance`) is enforced only in app code; a naive PG port races under concurrency | High | Use a transaction + partial unique index `WHERE status = 'active'`; add a contention test. |
| Neo4j driver/RAG cache invalidation on `neo4j_instance` writes is a side effect easy to drop during the port | High | Keep the `close_driver` / `clear_graph_rag_util` hook above the boundary and test it under both backends. |
| Two `CACHE_ENTITY_CONFIG` `list_resolver` paths point at `models.*` and break when modules move | Medium | Update paths in Phase 1; add an import test that loads every configured resolver path. |
| `document_process_error` is absent from cache config | Low | Decide inclusion during Phase 0 close-out. |
| Embedding fidelity (`content_embedding`) lost in JSONB write/read round-trip | Medium | Store as JSONB/`double precision[]`; assert round-trip equality in repository tests. `pgvector` only if PG-side vector search is later required. |
| AWS made conditional in PG mode but KGE still needs lambda/S3 | Medium | Confirm mandatory AWS services before gating; default to keeping AWS init unconditional unless proven optional. |
| Optional PostgreSQL deps leak into DynamoDB-only installs | Medium | Keep PG imports lazy; add a DynamoDB-only import test. |
| PG `register_all` / `_import_all_models` swallow `ImportError` (carried over from `rfq_engine`), hiding genuine import bugs | Medium | At minimum log the failure; consider failing loudly when `DB_BACKEND=postgresql` is the active backend. |
| PostgreSQL `list()` must hand-rebuild the `*ListType` shape that `resolve_list_decorator` produces on DynamoDB | Medium | Mirror `rfq_engine`'s PG `list` (count + offset/limit + `order_by`); assert identical connection shape/field names in backend-agnostic GraphQL tests. |

## Immediate Next Work

1. Close Phase 0: write `docs/PHASE0_ENTITY_INVENTORY.md` with per-field DynamoDB→PostgreSQL type mappings, and confirm mandatory AWS services in PG mode.
2. Start Phase 1: add `Config.DB_BACKEND`, the `models/repositories/` boundary, move PynamoDB modules under `models/dynamodb/`, and migrate all GraphQL call sites (including `schema.py` inline imports) to `get_repo()` / `get_loaders()`.
3. Add the static adoption guard test and the backend-agnostic dispatch test (DynamoDB arm first).
4. Only after Phase 1 is green, begin Phase 2 (PG foundation) and Phase 3 (5-entity port), starting with `document` and `graph_schema` to exercise JSONB, embeddings, and the single-active invariant early. No DynamoDB→PostgreSQL data migration is planned — both backends start empty.
