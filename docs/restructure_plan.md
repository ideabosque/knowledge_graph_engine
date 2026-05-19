# Knowledge Graph Engine - Restructure Plan

**Status**: Draft  
**Date**: 2026-05-19  
**Primary reference**: [data_model.md](./data_model.md)

## Purpose

This document turns the proposed v2 data model into an implementation plan that matches the current codebase.

The repository today is still built around a **single active schema** and **single active Neo4j instance** per `partition_key`. The target model introduces **multiple knowledge types per tenant partition**, each with its own schema, Neo4j routing, data sources, documents, and request history.

This plan is intentionally grounded in the current project layout:

- Runtime entrypoint: `knowledge_graph_engine/main.py`
- GraphQL schema surface: `knowledge_graph_engine/handlers/schema.py`
- Routing/state: `knowledge_graph_engine/handlers/config.py`, `knowledge_graph_engine/handlers/neo4j_connection_manager.py`
- Knowledge workflows: `knowledge_graph_engine/handlers/extractor.py`, `knowledge_graph_engine/handlers/search_handler.py`, `knowledge_graph_engine/handlers/rag_handler.py`, `knowledge_graph_engine/handlers/schema_resolver.py`
- Persistence: `knowledge_graph_engine/models/*.py`
- REST daemon: `knowledge_graph_engine/handlers/fastapi_app.py`

## What Must Change

The current architecture assumes this scope:

- one partition -> one active `Neo4jInstanceModel`
- one partition -> one active `GraphSchemaModel`
- documents and requests are only partition-scoped
- `document_source` is a free-form string

The v2 model requires this scope:

- one partition -> many `KnowledgeTypeModel` rows
- one knowledge type -> one active Neo4j instance at a time
- one knowledge type -> one active graph schema at a time
- one knowledge type -> many active data sources
- documents, requests, and process errors must all carry `knowledge_type_name`
- documents and process errors should reference `data_source_name`

## Corrections to the Earlier Draft

The earlier `restructure_plan.md` was directionally right, but it had a few design contradictions that would cause rework if implemented as written.

### 1. `KnowledgeTypeModel` should not be active-singleton scoped

The goal is to let one tenant host several concurrent domains such as `products`, `support_tickets`, and `internal_wiki`. That means:

- multiple knowledge types may be active in the same partition at the same time
- `KnowledgeTypeModel.status` is still useful for soft-disable/archive
- there should **not** be a `get_active_knowledge_type(partition_key)` helper that assumes one active row per partition

Recommended helper set:

- `get_knowledge_type(partition_key, knowledge_type_name)`
- `get_knowledge_types_for_partition(partition_key, statuses=None)`
- optional `require_active_knowledge_type(partition_key, knowledge_type_name)` for validation

### 2. `DataSourceModel` should support many active rows per knowledge type

`data_model.md` says a knowledge type ingests from many sources. That means multiple sources may be active simultaneously. So:

- `DataSourceModel.status` remains useful
- there should **not** be a "one active data source per knowledge type" invariant
- helper functions should query active sources, not enforce uniqueness

Recommended helper set:

- `get_data_source(partition_key, data_source_name)`
- `get_data_sources_for_knowledge_type(partition_key, knowledge_type_name, statuses=None)`
- `require_active_data_source(partition_key, knowledge_type_name, data_source_name)`

### 3. The GraphQL layer is not fully symmetrical today

The project does not consistently use `queries/*.py` for every entity:

- `document` and `graph_schema` use dedicated query modules
- `search` and `rag` use `queries/search.py`
- `neo4j_instance` and `request` are currently resolved directly inside `handlers/schema.py`

The migration plan should preserve working patterns first, then normalize later if the team wants that cleanup.

### 4. The migration has to account for current model gaps

The current code still has these realities:

- `DocumentProcessErrorModel` still uses `document_source`
- `ExecuteExtract` mutation still accepts `document_source`
- `fastapi_app.py` background extract endpoint still accepts `document_source`
- `initialize_tables()` must be extended manually as new models are added

The plan below explicitly calls these out.

## Design Principles

1. Preserve current behavior for existing clients during the transition.
2. Introduce `knowledge_type_name="default"` as the compatibility bridge.
3. Make routing changes first-class: cache keys, driver keys, and schema lookup must all move together.
4. Keep active-only invariants only where they make domain sense:
   - yes for `Neo4jInstanceModel`
   - yes for `GraphSchemaModel`
   - no for `KnowledgeTypeModel`
   - no for `DataSourceModel`
5. Prefer fail-closed validation once migration is complete.

## Target Scope

### New entities

- `KnowledgeTypeModel`
- `DataSourceModel`

### Existing entities to extend

- `Neo4jInstanceModel`
- `GraphSchemaModel`
- `DocumentModel`
- `RequestModel`
- `DocumentProcessErrorModel`

### Runtime components to refactor

- `Config.get_graph_rag_util()`
- `Neo4jConnectionManager`
- `SchemaResolver`
- `Extractor`
- `SearchHandler`
- `RAGHandler`
- GraphQL schema and mutation/query adapters
- FastAPI background extract endpoint

## Phase 0: Decision Record and Guardrails

### Goals

- Confirm the final scoping rules from `data_model.md`
- Decide index strategy before model files are changed
- Freeze unrelated model-layer refactors while this branch is active

### Decisions to record

1. `KnowledgeTypeModel`: many active rows per partition allowed
2. `DataSourceModel`: many active rows per knowledge type allowed
3. `Neo4jInstanceModel`: one active row per `(partition_key, knowledge_type_name)`
4. `GraphSchemaModel`: one active row per `(partition_key, knowledge_type_name)`
5. `document_source` is transitional only and will be replaced by `data_source_name`

### Acceptance criteria

- All five decisions above are explicitly approved in this file
- The team chooses between:
  - secondary indexes on `knowledge_type_name`, or
  - composite range keys where appropriate

## Phase 1: Introduce New Core Models

### 1.1 Add `KnowledgeTypeModel`

Create:

- `knowledge_graph_engine/models/knowledge_type.py`
- `knowledge_graph_engine/types/knowledge_type.py`
- `knowledge_graph_engine/mutations/knowledge_type.py`

Optional, depending on whether the team wants symmetry immediately:

- `knowledge_graph_engine/queries/knowledge_type.py`

Required fields:

- `partition_key`
- `knowledge_type_name`
- `endpoint_id`
- `part_id`
- `description`
- `status`
- `updated_by`
- `created_at`
- `updated_at`

Required behavior:

- CRUD support aligned with existing decorator patterns
- list resolver filtered by `partition_key` and optional `status`
- helper to validate that a named knowledge type exists and is active

### 1.2 Add `DataSourceModel`

Create:

- `knowledge_graph_engine/models/data_source.py`
- `knowledge_graph_engine/types/data_source.py`
- `knowledge_graph_engine/mutations/data_source.py`

Optional:

- `knowledge_graph_engine/queries/data_source.py`

Required fields:

- `partition_key`
- `data_source_name`
- `knowledge_type_name`
- `endpoint_id`
- `part_id`
- `source_type`
- `config`
- `status`
- `updated_by`
- `created_at`
- `updated_at`

Required behavior:

- CRUD support
- query by `knowledge_type_name`
- validation helper to ensure a data source belongs to the expected knowledge type

### 1.3 Register the new models in the runtime

Update:

- `knowledge_graph_engine/handlers/schema.py`
- `knowledge_graph_engine/models/utils.py`
- `knowledge_graph_engine/models/__init__.py`
- `knowledge_graph_engine/handlers/config.py`

### Acceptance criteria

- New tables can be created via `initialize_tables()`
- New GraphQL types/mutations are visible
- Unit tests cover basic CRUD and validation

## Phase 2: Extend Existing Models with Knowledge Type Scope

### 2.1 Add `knowledge_type_name` to existing tables

Update these model files:

- `knowledge_graph_engine/models/neo4j_instance.py`
- `knowledge_graph_engine/models/graph_schema.py`
- `knowledge_graph_engine/models/document.py`
- `knowledge_graph_engine/models/request.py`
- `knowledge_graph_engine/models/document_process_error.py`

### 2.2 Replace `document_source` with `data_source_name`

Update these model and workflow files:

- `knowledge_graph_engine/models/document.py`
- `knowledge_graph_engine/models/document_process_error.py`
- `knowledge_graph_engine/mutations/extract.py`
- `knowledge_graph_engine/handlers/extractor.py`
- `knowledge_graph_engine/handlers/fastapi_app.py`
- `knowledge_graph_engine/types/document.py`
- `knowledge_graph_engine/types/document_process_error.py`

Transition rule:

- keep reading old `document_source` data during migration
- stop writing new `document_source` values once `data_source_name` is available

### 2.3 Re-scope active helpers

These helpers must change from partition scope to knowledge-type scope:

- `get_active_neo4j_instance(partition_key)` -> `get_active_neo4j_instance(partition_key, knowledge_type_name)`
- `_deactivate_current_active_instance(...)`
- `get_active_graph_schema(partition_key)` -> `get_active_graph_schema(partition_key, knowledge_type_name)`
- `_deactivate_current_active_schema(...)`

### Acceptance criteria

- Existing models compile and persist with `knowledge_type_name`
- Active-instance and active-schema logic is knowledge-type scoped
- Document and process error writes support `data_source_name`

## Phase 3: Routing and Cache Refactor

This is the highest-risk phase because it changes runtime identity.

### 3.1 Update driver cache keys

Refactor `knowledge_graph_engine/handlers/neo4j_connection_manager.py`:

- `_drivers` key changes from `partition_key` to `(partition_key, knowledge_type_name)`
- `get_driver()`, `close_driver()`, and `close_all()` update accordingly

### 3.2 Update `Config.get_graph_rag_util()`

Refactor `knowledge_graph_engine/handlers/config.py`:

- `_graph_rag_utils` key changes from `partition_key` to `(partition_key, knowledge_type_name)`
- `get_graph_rag_util(partition_key, knowledge_type_name)`
- `clear_graph_rag_util(partition_key, knowledge_type_name)`

### 3.3 Update cache metadata

`CACHE_ENTITY_CONFIG` and `CACHE_RELATIONSHIPS` need to be expanded for:

- `knowledge_type`
- `data_source`
- `document_process_error`

Also align the resolver paths with the actual implementation style used in the repository. Do not assume every list resolver lives in `queries/`.

### Acceptance criteria

- Separate knowledge types in the same partition get separate drivers
- Separate knowledge types in the same partition get separate `GraphRAGUtil` instances
- Cache invalidation config reflects the real module layout

## Phase 4: Schema Resolution and Workflow Refactor

### 4.1 `SchemaResolver`

Refactor `knowledge_graph_engine/handlers/schema_resolver.py`:

- constructor accepts `knowledge_type_name`
- active schema lookup is scoped to knowledge type
- schema save writes `knowledge_type_name`

### 4.2 `Extractor`

Refactor `knowledge_graph_engine/handlers/extractor.py`:

- accept `knowledge_type_name`
- accept `data_source_name`
- validate knowledge type existence
- validate data source existence or create a backward-compatible default/manual source during transition
- persist documents and process errors with `knowledge_type_name`
- route through `Config.get_graph_rag_util(partition_key, knowledge_type_name)`

### 4.3 `SearchHandler` and `RAGHandler`

Refactor:

- `knowledge_graph_engine/handlers/search_handler.py`
- `knowledge_graph_engine/handlers/rag_handler.py`

Changes:

- accept `knowledge_type_name`
- load active schema per knowledge type
- persist `RequestModel` with `knowledge_type_name`

### Acceptance criteria

- Extract, search, and RAG all operate within a knowledge-type boundary
- Request logging is knowledge-type scoped
- Schema save/load logic is knowledge-type scoped

## Phase 5: GraphQL and REST Contract Expansion

### 5.1 GraphQL

Update `knowledge_graph_engine/handlers/schema.py` and mutation/query adapters to:

- add `knowledge_type_name` to extract, search, and rag operations
- replace `document_source` with `data_source_name`
- expose CRUD for `KnowledgeTypeModel` and `DataSourceModel`

Transition behavior:

- `knowledge_type_name` defaults to `"default"` until migration is complete
- after client rollout, make it required

### 5.2 REST daemon

Update `knowledge_graph_engine/handlers/fastapi_app.py`:

- `POST /{endpoint_id}/extract` accepts `knowledge_type_name`
- request body uses `data_source_name`
- background task state includes the knowledge type for traceability

### Acceptance criteria

- GraphQL schema exposes the new arguments and entities
- REST extract endpoint can target a specific knowledge type
- Existing clients still work with the `"default"` fallback

## Phase 6: Data Migration and Backfill

### 6.1 New table creation

Create:

- `kge-knowledge_types`
- `kge-data_sources`

### 6.2 Default knowledge type backfill

For every existing `partition_key`:

1. create `KnowledgeTypeModel(partition_key, "default")`
2. set `knowledge_type_name="default"` on:
   - `Neo4jInstanceModel`
   - `GraphSchemaModel`
   - `DocumentModel`
   - `RequestModel`
   - `DocumentProcessErrorModel`

### 6.3 Data source backfill

1. collect distinct `document_source` values per partition
2. create `DataSourceModel` rows under `knowledge_type_name="default"`
3. copy `document_source` -> `data_source_name` on documents and process errors

### 6.4 Transitional read/write behavior

Until all clients are updated:

- read old rows that only contain `document_source`
- write `data_source_name`
- optionally mirror to `document_source` for a short transition window if operationally necessary

### Acceptance criteria

- migration is idempotent
- counts reconcile before and after backfill
- old partitions remain queryable through the `"default"` knowledge type

## Phase 7: Validation and Test Expansion

### New unit tests

- `tests/test_knowledge_type.py`
- `tests/test_data_source.py`
- `tests/test_cache.py` or equivalent cache-focused coverage
- `tests/test_v2_migration.py`

### Existing tests to expand

- `tests/test_extract.py`
- `tests/test_search.py`
- `tests/test_search_rag.py`
- `tests/test_integration.py`
- `tests/test_module_hardening.py`
- `tests/test_daemon.py`

### Critical validation scenarios

1. Same partition, two knowledge types, different active schemas
2. Same partition, two knowledge types, different Neo4j instances
3. Extraction into one knowledge type does not leak into another
4. Search and RAG only read from the targeted knowledge type
5. Cache invalidation does not cross knowledge-type boundaries accidentally
6. Migration can be re-run safely

## Recommended Sequence

Implement in this order:

1. Add new model files and table registration
2. Add `knowledge_type_name` to old models
3. Refactor routing and cache keys
4. Refactor schema resolution and handlers
5. Expand GraphQL and REST contracts
6. Add migration script
7. Tighten validation and remove transitional fallbacks

This order minimizes the window where the persistence model and runtime routing disagree.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Routing cache still keyed only by partition | High | Refactor `Neo4jConnectionManager` and `Config` in the same phase |
| Contradictory active-status rules for knowledge types or data sources | High | Keep active-singleton logic only for schema and Neo4j instance |
| Backfill misses `DocumentProcessErrorModel` | Medium | Treat it as a first-class migration target, not a follow-up |
| GraphQL contract drifts from handler signatures | Medium | Update `handlers/schema.py`, mutation classes, and integration tests together |
| Cache invalidation points to the wrong resolver paths | Medium | Align config with the actual repository structure before writing new tests |

## Done Definition

The restructure is complete when all of the following are true:

- `KnowledgeTypeModel` and `DataSourceModel` are live
- all runtime operations accept `knowledge_type_name`
- active Neo4j instance and active graph schema are scoped to knowledge type
- documents, requests, and process errors persist `knowledge_type_name`
- document ingestion uses `data_source_name`
- tests prove isolation between two knowledge types in the same partition
- the `"default"` fallback can be removed without breaking production clients

## File Checklist

### New files

- `knowledge_graph_engine/models/knowledge_type.py`
- `knowledge_graph_engine/models/data_source.py`
- `knowledge_graph_engine/types/knowledge_type.py`
- `knowledge_graph_engine/types/data_source.py`
- `knowledge_graph_engine/mutations/knowledge_type.py`
- `knowledge_graph_engine/mutations/data_source.py`
- optional: `knowledge_graph_engine/queries/knowledge_type.py`
- optional: `knowledge_graph_engine/queries/data_source.py`
- migration script under a new `scripts/` or `tools/` location

### Modified files

- `knowledge_graph_engine/handlers/config.py`
- `knowledge_graph_engine/handlers/neo4j_connection_manager.py`
- `knowledge_graph_engine/handlers/schema_resolver.py`
- `knowledge_graph_engine/handlers/extractor.py`
- `knowledge_graph_engine/handlers/search_handler.py`
- `knowledge_graph_engine/handlers/rag_handler.py`
- `knowledge_graph_engine/handlers/schema.py`
- `knowledge_graph_engine/handlers/fastapi_app.py`
- `knowledge_graph_engine/models/document.py`
- `knowledge_graph_engine/models/graph_schema.py`
- `knowledge_graph_engine/models/neo4j_instance.py`
- `knowledge_graph_engine/models/request.py`
- `knowledge_graph_engine/models/document_process_error.py`
- `knowledge_graph_engine/models/utils.py`
- `knowledge_graph_engine/models/cache.py`
- `knowledge_graph_engine/mutations/extract.py`
- `knowledge_graph_engine/queries/search.py`
- GraphQL type files affected by new fields

