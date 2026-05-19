# Knowledge Graph Engine — Restructure Plan

**Status**: Draft
**Date**: 2026-05-19
**Primary reference**: [data_model.md](./data_model.md)
**Related**: [development_plan.md](./development_plan.md)

## Purpose

Turn the proposed v2 data model into an implementation plan that maps cleanly onto the current codebase. The plan is grounded in verified file paths and named symbols, so any reader can cross-check it against the repository.

The repository today is built around **one active schema and one active Neo4j instance per `partition_key`**. The target model introduces **`KnowledgeTypeModel`** as a per-tenant sub-scope, with its own schema, Neo4j instance, data sources, documents, and request history.

### Current code anchors

- Runtime entrypoint: [main.py](../knowledge_graph_engine/main.py) — `KnowledgeGraphEngine`, `_apply_partition_defaults()`
- GraphQL surface: [handlers/schema.py](../knowledge_graph_engine/handlers/schema.py) — `Query`, `Mutations`, `type_class()`
- Routing/state: [handlers/config.py](../knowledge_graph_engine/handlers/config.py), [handlers/neo4j_connection_manager.py](../knowledge_graph_engine/handlers/neo4j_connection_manager.py)
- Knowledge workflows: [handlers/extractor.py](../knowledge_graph_engine/handlers/extractor.py), [handlers/search_handler.py](../knowledge_graph_engine/handlers/search_handler.py), [handlers/rag_handler.py](../knowledge_graph_engine/handlers/rag_handler.py), [handlers/schema_resolver.py](../knowledge_graph_engine/handlers/schema_resolver.py)
- Persistence: [models/](../knowledge_graph_engine/models/)
- REST daemon: [handlers/fastapi_app.py](../knowledge_graph_engine/handlers/fastapi_app.py)

---

## What Must Change

| Concern | Today | Target |
|---|---|---|
| Tenant scoping | `partition_key` (`endpoint_id#part_id`) | `(partition_key, knowledge_type_name)` |
| Neo4j instance per partition | One active row | One active per `(partition_key, knowledge_type_name)` |
| Graph schema per partition | One active row | One active per `(partition_key, knowledge_type_name)` |
| Data source | Free-form `document_source` string on `DocumentModel` | First-class `DataSourceModel` row, FK from `DocumentModel.data_source_name` |
| Documents / requests / errors | `partition_key`-scoped only | Also carry `knowledge_type_name` (and `data_source_name` where applicable) |
| Driver and `GraphRAGUtil` caches | Keyed by `partition_key` | Keyed by `(partition_key, knowledge_type_name)` |
| Vector index bootstrap | One per Neo4j instance | One per knowledge type's Neo4j instance |

`DataSourceModel` was previously dropped from scope (see [development_plan.md Key Decisions Log → 2026-04](./development_plan.md#key-decisions-log)) in favor of the free-form `document_source` string. The v2 model re-introduces it as a first-class entity because connector config, audit trail, and re-ingestion need it.

---

## Key Design Decisions

### 1. `KnowledgeTypeModel` is not active-singleton scoped

Multiple knowledge types may be active in the same partition at the same time (the whole point — one tenant can host `products` and `support_tickets` concurrently). `KnowledgeTypeModel.status` remains useful for soft-disable/archive, but there is **no** `get_active_knowledge_type(partition_key)` helper.

Helper set:

- `get_knowledge_type(partition_key, knowledge_type_name)`
- `get_knowledge_types_for_partition(partition_key, statuses=None)`
- `require_active_knowledge_type(partition_key, knowledge_type_name)` for validation

### 2. `DataSourceModel` supports many active rows per knowledge type

A knowledge type may ingest from several sources simultaneously (`woocommerce_main`, `manual_csv`, `support_api`). There is **no** "one active data source per knowledge type" invariant. The `status` field exists for disable/archive, not uniqueness.

> **Note for `data_model.md`**: the "One Active per Knowledge Type" section in [data_model.md](./data_model.md#one-active-per-knowledge-type) currently lists `DataSourceModel` alongside `Neo4jInstanceModel` and `GraphSchemaModel`. That entry should be removed — see this decision for rationale.

Helper set:

- `get_data_source(partition_key, data_source_name)`
- `get_data_sources_for_knowledge_type(partition_key, knowledge_type_name, statuses=None)`
- `require_active_data_source(partition_key, knowledge_type_name, data_source_name)`

### 3. Active-singleton invariant remains for schema and Neo4j instance, re-scoped

`Neo4jInstanceModel` and `GraphSchemaModel` keep the existing "one active row" pattern, but the scope changes from `partition_key` to `(partition_key, knowledge_type_name)`. Versioning history is still preserved by flipping old rows to `status="inactive"` rather than deleting.

### 4. GraphQL resolver layout is not normalized in this plan

The current code mixes resolver locations:

- `document` and `graph_schema` have dedicated modules under `queries/`
- `search` and `rag` use `queries/search.py`
- `neo4j_instance` and `request` are inlined in `handlers/schema.py`

This plan preserves the existing pattern per entity to keep the diff focused. Normalizing resolver layout is out of scope and can be done later as a cleanup if the team chooses.

### 5. `endpoint_id` and `part_id` redundancy is preserved

Every table will continue to carry `endpoint_id`, `part_id`, and `partition_key` even though the first two are derivable from the third. Removing them would touch every model write — out of scope for this restructure.

---

## Compatibility Strategy

The restructure must not break existing clients. The strategy across phases:

1. **`knowledge_type_name="default"` is the transitional value.** During Phase 6 backfill, every existing `partition_key` gets a `KnowledgeTypeModel` row named `"default"`, and every existing `Neo4jInstance`, `GraphSchema`, `Document`, `Request`, and `DocumentProcessError` row is stamped with `knowledge_type_name="default"`.
2. **GraphQL and REST parameters default to `"default"`** when `knowledge_type_name` is omitted — until clients are migrated.
3. **`document_source` is read but not written** once `data_source_name` is in place. Old rows remain queryable.
4. **Fail-closed validation is added after migration**. Once telemetry confirms all callers pass `knowledge_type_name`, the `"default"` fallback is removed and missing values raise — mirroring the partition_key fail-closed pattern from [development_plan.md §4](./development_plan.md#4-close-partition_key-fail-open-paths-done-2026-05-13).

---

## Phase 0 — Decisions and Guardrails

**Goal**: lock in the design choices before any code changes.

### Decisions to record explicitly

1. `KnowledgeTypeModel`: many active rows per partition allowed
2. `DataSourceModel`: many active rows per knowledge type allowed
3. `Neo4jInstanceModel`: one active row per `(partition_key, knowledge_type_name)`
4. `GraphSchemaModel`: one active row per `(partition_key, knowledge_type_name)`
5. `document_source` is transitional only and will be replaced by `data_source_name`
6. Indexing choice per table: LSI on `knowledge_type_name` for small/medium tables; **GSI for `kge-documents`** (per-tenant size can exceed the 10 GB LSI limit) — see [data_model.md Indexing Strategy](./data_model.md#indexing-strategy-lsi-vs-gsi)

### Patch `data_model.md`

Remove `DataSourceModel` from the "One Active per Knowledge Type" list (decision #2 above contradicts the current text).

### Acceptance

- All six decisions are approved in this file
- `data_model.md` is updated to match decision #2
- No code changes yet

---

## Phase 1 — Introduce `KnowledgeTypeModel` and `DataSourceModel`

### 1.1 `KnowledgeTypeModel`

New files:

- `knowledge_graph_engine/models/knowledge_type.py`
- `knowledge_graph_engine/types/knowledge_type.py`
- `knowledge_graph_engine/mutations/knowledge_type.py`
- *(optional)* `knowledge_graph_engine/queries/knowledge_type.py` — only if the team wants the symmetric layout immediately

Required fields: `partition_key` (PK hash), `knowledge_type_name` (PK range), `endpoint_id`, `part_id`, `description`, `status`, `updated_by`, `created_at`, `updated_at`.

Required behavior: CRUD aligned with existing decorator patterns (`@insert_update_decorator`, `@delete_decorator`, `@resolve_list_decorator`); list resolver filtered by `partition_key` and optional `statuses`; `require_active_knowledge_type()` validation helper.

### 1.2 `DataSourceModel`

New files:

- `knowledge_graph_engine/models/data_source.py`
- `knowledge_graph_engine/types/data_source.py`
- `knowledge_graph_engine/mutations/data_source.py`
- *(optional)* `knowledge_graph_engine/queries/data_source.py`

Required fields: `partition_key` (PK hash), `data_source_name` (PK range), `knowledge_type_name` (FK), `endpoint_id`, `part_id`, `source_type`, `config` (Map), `status`, `updated_by`, `created_at`, `updated_at`.

Required behavior: CRUD; query by `knowledge_type_name`; `require_active_data_source(partition_key, knowledge_type_name, data_source_name)`.

### 1.3 Register new models

- Add to `initialize_tables()` in [models/utils.py](../knowledge_graph_engine/models/utils.py) — currently registers 5 models manually; will become 7.
- Add lazy imports in [models/__init__.py](../knowledge_graph_engine/models/__init__.py).
- Add types and mutations to `type_class()` and `Mutations` in [handlers/schema.py](../knowledge_graph_engine/handlers/schema.py).
- Add cache config in [handlers/config.py](../knowledge_graph_engine/handlers/config.py) — see Phase 3 for the full updated `CACHE_ENTITY_CONFIG` and `CACHE_RELATIONSHIPS`.

### Acceptance

- New tables created via `initialize_tables()`
- New GraphQL types and mutations visible
- Unit tests cover CRUD and validation helpers

---

## Phase 2 — Extend Existing Models with Knowledge-Type Scope

### 2.1 Add `knowledge_type_name` to existing tables

Add as a non-key attribute on:

- [models/neo4j_instance.py](../knowledge_graph_engine/models/neo4j_instance.py)
- [models/graph_schema.py](../knowledge_graph_engine/models/graph_schema.py)
- [models/document.py](../knowledge_graph_engine/models/document.py)
- [models/request.py](../knowledge_graph_engine/models/request.py)
- [models/document_process_error.py](../knowledge_graph_engine/models/document_process_error.py)

Decide per table whether to add an LSI/GSI on `knowledge_type_name` based on actual query patterns (see [data_model.md Indexing Strategy](./data_model.md#indexing-strategy-lsi-vs-gsi)). At minimum, `kge-documents` should use a **GSI** because per-tenant size can exceed the 10 GB LSI limit.

### 2.2 Replace `document_source` with `data_source_name`

Verified current usages (need updating):

- [models/document_process_error.py:27](../knowledge_graph_engine/models/document_process_error.py#L27) — model attribute
- [mutations/extract.py:18](../knowledge_graph_engine/mutations/extract.py#L18) — GraphQL mutation argument
- [handlers/fastapi_app.py:256](../knowledge_graph_engine/handlers/fastapi_app.py#L256) — background extract endpoint
- [handlers/extractor.py:41,85,130,210,221](../knowledge_graph_engine/handlers/extractor.py#L41) — workflow plumbing
- `types/document.py`, `types/document_process_error.py` — GraphQL type fields

Transition rule:

- Continue reading old rows that only have `document_source`
- Stop writing new `document_source` values once `data_source_name` is available
- Optional short-term mirror of `data_source_name` → `document_source` if external dashboards depend on the old field

### 2.3 Re-scope active helpers

Signature changes:

- `get_active_neo4j_instance(partition_key)` → `get_active_neo4j_instance(partition_key, knowledge_type_name)`
- `_deactivate_current_active_instance(partition_key, exclude_instance_id=None)` → adds `knowledge_type_name`
- `get_active_graph_schema(partition_key)` → `get_active_graph_schema(partition_key, knowledge_type_name)`
- `_deactivate_current_active_schema(partition_key, exclude_schema_name=None)` → adds `knowledge_type_name`

Cache the `@method_cache` keys include the new dimension.

### Acceptance

- Existing models persist with `knowledge_type_name`
- Active-instance and active-schema queries are knowledge-type scoped
- Document and process-error writes accept `data_source_name`

---

## Phase 3 — Routing and Cache Refactor

**Highest-risk phase** — changes runtime identity. Driver and `GraphRAGUtil` caches change key shape; misalignment between cache key and lookup logic will cause cross-knowledge-type bleed.

### 3.1 Driver cache keys

In [handlers/neo4j_connection_manager.py](../knowledge_graph_engine/handlers/neo4j_connection_manager.py):

- `Neo4jConnectionManager._drivers` keyed by tuple `(partition_key, knowledge_type_name)` instead of `partition_key`
- `get_driver(partition_key, knowledge_type_name)` — both params required, fail-closed
- `close_driver(partition_key, knowledge_type_name)` — same
- `close_all()` — iterates the new key shape and calls `Config.clear_graph_rag_util(pk, kt)` for each

### 3.2 `Config.get_graph_rag_util`

In [handlers/config.py](../knowledge_graph_engine/handlers/config.py):

- `_graph_rag_utils` keyed by tuple `(partition_key, knowledge_type_name)`
- `get_graph_rag_util(partition_key, knowledge_type_name)` calls `get_active_neo4j_instance(partition_key, knowledge_type_name)` (re-scoped from Phase 2.3)
- `clear_graph_rag_util(partition_key, knowledge_type_name)`

The instance-lookup-failure-propagates behavior from [development_plan.md §4](./development_plan.md#4-close-partition_key-fail-open-paths-done-2026-05-13) is preserved — no silent fallback to `database="neo4j"`.

### 3.3 `Extractor.bootstrap_indexes_if_missing`

The auto-vector-index bootstrap added in [development_plan.md §3](./development_plan.md#3-operational-hardening-done-2026-05-13) currently runs once per Neo4j instance. After this refactor, each knowledge type's Neo4j instance gets its own bootstrap call — no shared index across knowledge types within a partition.

### 3.4 Cache metadata

Expand `CACHE_ENTITY_CONFIG` to include `knowledge_type`, `data_source`, `document_process_error`. Match resolver-path style to the actual implementation: list resolvers for `neo4j_instance` and `request` are in `models/`, not `queries/` (this is already correct in the current config — see [config.py:91-104](../knowledge_graph_engine/handlers/config.py#L91-L104) — preserve that asymmetry for the new entities too).

Expand `CACHE_RELATIONSHIPS` to reflect the new hierarchy:

```python
CACHE_RELATIONSHIPS = {
    "knowledge_type": [
        "neo4j_instance", "graph_schema", "data_source",
        "document", "request", "document_process_error",
    ],
    "data_source": ["document", "document_process_error"],
    "document":    ["request"],
    "graph_schema": ["document"],   # preserved from current
    "neo4j_instance": [],           # preserved from current
}
```

### Acceptance

- Two knowledge types in the same partition return different drivers and different `GraphRAGUtil` instances
- Each knowledge type's Neo4j instance has its own bootstrapped `vector` index
- Cache invalidation config aligns with the real module layout
- All 4 list resolvers still fail-closed on missing `partition_key`; they now also fail-closed on missing `knowledge_type_name` when the kwarg is required

---

## Phase 4 — Schema Resolution and Workflow Refactor

### 4.1 `SchemaResolver`

In [handlers/schema_resolver.py](../knowledge_graph_engine/handlers/schema_resolver.py):

- Constructor accepts `knowledge_type_name`
- `_load_active_schema()` and `evolve_schema_from_graph(text)` scope to `(partition_key, knowledge_type_name)`
- `_save_as_active()` writes `knowledge_type_name` on the new row and deactivates only the prior active row for the same `(partition_key, knowledge_type_name)`

### 4.2 `Extractor`

In [handlers/extractor.py](../knowledge_graph_engine/handlers/extractor.py):

- `extract()` accepts `knowledge_type_name` (defaults to `"default"` during transition) and `data_source_name`
- Validates knowledge type exists and is active before calling `Config.get_graph_rag_util(partition_key, knowledge_type_name)`
- Validates data source exists and is active before persisting; during transition, missing `data_source_name` auto-creates or maps to a `default` source row
- Persists `DocumentModel` and `DocumentProcessErrorModel` with `knowledge_type_name`
- Post-extract calls `bootstrap_indexes_if_missing()` on the per-knowledge-type instance
- Post-extract calls `evolve_schema_from_graph(text)` on the per-knowledge-type `SchemaResolver`

### 4.3 `SearchHandler` and `RAGHandler`

In [handlers/search_handler.py](../knowledge_graph_engine/handlers/search_handler.py) and [handlers/rag_handler.py](../knowledge_graph_engine/handlers/rag_handler.py):

- Accept `knowledge_type_name`
- Load active schema per `(partition_key, knowledge_type_name)`
- Route through `Config.get_graph_rag_util(partition_key, knowledge_type_name)`
- Persist `RequestModel` with `knowledge_type_name`

### Acceptance

- Extract, search, and RAG all operate within a knowledge-type boundary
- Request logging is knowledge-type scoped
- Schema save/load logic is knowledge-type scoped
- Vector index bootstrap is per-knowledge-type

---

## Phase 5 — GraphQL and REST Contract Expansion

### 5.1 GraphQL

Update [handlers/schema.py](../knowledge_graph_engine/handlers/schema.py) and the affected mutation/query adapters:

- `executeExtract` mutation: add `knowledge_type_name`, replace `document_source` with `data_source_name`
- `search` query: add `knowledge_type_name`
- `rag` query: add `knowledge_type_name`
- Expose CRUD for `KnowledgeTypeModel` and `DataSourceModel` (mutations + queries)
- Update `Query.request_list` and `Query.neo4j_instance_list` to accept `knowledge_type_name` filter

Transition: `knowledge_type_name` defaults to `"default"` until clients migrate, then becomes required.

### 5.2 REST daemon

Update [handlers/fastapi_app.py](../knowledge_graph_engine/handlers/fastapi_app.py):

- `POST /{endpoint_id}/extract`: request body accepts `knowledge_type_name` and `data_source_name` (replacing `document_source`)
- Optional `Knowledge-Type` header as a daemon-level alternative to body field
- Background task state includes `knowledge_type_name` for traceability and per-task logging

### Acceptance

- GraphQL schema exposes new arguments and entities
- REST extract endpoint can target a specific knowledge type
- Existing clients still work via `"default"` fallback

---

## Phase 6 — Data Migration and Backfill

### 6.1 New table creation

Create `kge-knowledge_types` and `kge-data_sources` via `initialize_tables()` or explicit `model.create_table(...)` call.

### 6.2 Default knowledge type backfill

For every existing `partition_key`:

1. Create `KnowledgeTypeModel(partition_key, "default")` with `status="active"`.
2. Set `knowledge_type_name="default"` on every existing row of:
   - `Neo4jInstanceModel`
   - `GraphSchemaModel` (including all inactive versions)
   - `DocumentModel`
   - `RequestModel`
   - `DocumentProcessErrorModel`

### 6.3 Data source backfill

1. Collect distinct `document_source` values per partition by querying `DocumentModel`.
2. Create one `DataSourceModel` row per unique source, under `knowledge_type_name="default"`, with `source_type = document_source` and a minimal `config = {}`.
3. Copy `document_source` → `data_source_name` on every `DocumentModel` and `DocumentProcessErrorModel` row.
4. Leave `document_source` populated for now (read-only); drop the field in a follow-up release once telemetry confirms no readers remain.

### 6.4 Idempotency

The migration script must be re-runnable:

- `KnowledgeTypeModel("default")` insert uses upsert semantics (skip if exists)
- `DataSourceModel` create-or-skip based on `(partition_key, data_source_name)`
- Per-row updates check whether `knowledge_type_name` or `data_source_name` is already set before writing

### Acceptance

- Migration is idempotent (running twice produces the same result)
- Row counts reconcile before and after
- Old partitions remain queryable through the `"default"` knowledge type

---

## Phase 7 — Validation and Tightening

### 7.1 New unit tests

- `tests/test_knowledge_type.py` — CRUD + validation helpers
- `tests/test_data_source.py` — CRUD + per-knowledge-type listing
- `tests/test_v2_migration.py` — backfill idempotency

### 7.2 Extend existing tests

- `tests/test_extract.py` — extract with explicit `knowledge_type_name`
- `tests/test_search.py`, `tests/test_search_rag.py` — same
- `tests/test_integration.py` — daemon flow end-to-end with knowledge type
- `tests/test_module_hardening.py` — fail-closed on missing `knowledge_type_name` (mirror the existing partition_key fail-closed tests)
- `tests/test_daemon.py` — REST endpoint with the new fields

### 7.3 Critical scenarios to cover

1. Same partition, two knowledge types, different active schemas — schema A is not visible to knowledge type B
2. Same partition, two knowledge types, different Neo4j instances — graph A is not visible from knowledge type B
3. Extraction into knowledge type A does not write into B's Neo4j
4. Vector index bootstrap creates separate indexes for A and B
5. Search and RAG only read from the targeted knowledge type
6. Cache invalidation cascades within a knowledge type but not across
7. Migration can be re-run safely on a partially-migrated table

### 7.4 Fail-closed transition

After client telemetry shows zero requests without `knowledge_type_name`:

- Drop the `"default"` fallback in GraphQL/REST adapters
- Make `knowledge_type_name` required on all extract/search/rag operations
- List resolvers raise `ValueError("knowledge_type_name is required in context")` when the kwarg is expected, mirroring the partition_key pattern

### Acceptance

- All seven scenarios above pass
- Fail-closed behavior matches the partition_key model
- `"default"` fallback can be removed without breaking production clients

---

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Driver/`GraphRAGUtil` cache key changes ship before lookup logic does | High | Phase 3 changes both in the same commit; integration test must exercise two-knowledge-type isolation in one partition |
| Mistakenly applying active-singleton invariant to `KnowledgeTypeModel` or `DataSourceModel` | High | Decision recorded in Phase 0; helper API explicitly omits `get_active_*` for these two entities |
| Backfill misses `DocumentProcessErrorModel` (only model that still uses raw `document_source`) | Medium | Migration script enumerates all 5 affected models; integration test asserts every row has `knowledge_type_name` |
| GraphQL contract drifts from handler signatures | Medium | Update `handlers/schema.py`, mutation classes, and handlers in the same commit; smoke test queries each new field |
| Cache invalidation paths get out-of-date entity-type strings | Medium | Update `CACHE_RELATIONSHIPS` and `CACHE_ENTITY_CONFIG` in the same diff that adds the new models |
| `data_model.md` and `restructure_plan.md` disagree on `DataSourceModel` active-singleton | Medium | Phase 0 explicitly patches `data_model.md` |
| `default` fallback never gets removed | Low | Phase 7.4 lists the drop as an acceptance gate |

---

## Done Definition

The restructure is complete when all of the following are true:

- `KnowledgeTypeModel` and `DataSourceModel` are live
- All runtime operations accept `knowledge_type_name`
- Active Neo4j instance and active graph schema are scoped to `(partition_key, knowledge_type_name)`
- Driver cache, `GraphRAGUtil` cache, and vector index bootstrap are per-knowledge-type
- Documents, requests, and process errors persist `knowledge_type_name`
- Document ingestion uses `data_source_name`; `document_source` is no longer written
- Integration tests prove isolation between two knowledge types in the same partition
- The `"default"` fallback has been removed from extract/search/rag without breaking production clients
