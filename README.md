# Knowledge Graph Engine

`knowledge_graph_engine` is a SilvaEngine module for extracting entities and relationships from text, storing them in tenant-isolated Neo4j instances, and exposing search and RAG flows through GraphQL-compatible engine entrypoints.

## Current Shape

The current package is focused on **engine/runtime logic**, not HTTP hosting.

- Multi-tenant routing uses `partition_key = "{endpoint_id}#{part_id}"`.
- Each partition resolves one active Neo4j instance and one active graph schema.
- Extraction, search, and RAG all run against that tenant-scoped graph context.
- HTTP gateway, auth, and FastAPI hosting were moved out to `silvaengine_gateway`.

## Entry Points

### Engine usage

```python
import logging

from knowledge_graph_engine import KnowledgeGraphEngine, deploy

logger = logging.getLogger(__name__)
settings = {
    "region_name": "us-east-1",
    "aws_access_key_id": "...",
    "aws_secret_access_key": "...",
    "endpoint_id": "endpoint-001",
    "part_id": "part-001",
    "llm_type": "openai",
    "llm_name": "gpt-4o",
    "openai_api_key": "...",
}

engine = KnowledgeGraphEngine(logger, **settings)
services = deploy()

result = engine.knowledge_graph_graphql(
    context={},
    query="""
    query Search($queryText: String!) {
      search(queryText: $queryText, searchMode: "vector") {
        results
        total
      }
    }
    """,
    variables={"queryText": "What does Acme build?"},
)
```

### Gateway integration

The gateway should call the module-level dispatch functions exposed from [main.py](C:\Users\bibo7\gitrepo\silvaengine\knowledge_graph_engine\knowledge_graph_engine\main.py):

- `knowledge_graph_engine.main:dispatch_graphql`
- `knowledge_graph_engine.main:dispatch_extract`

These functions create a short-lived engine instance using the already-initialized `Config` singleton.

### Standalone invocation

`python -m knowledge_graph_engine` is kept as a deprecation stub and only emits a warning. New deployments should run `silvaengine_gateway`.

## Dual-Backend Persistence

KGE supports two selectable persistence backends for its five metadata entities
(documents, graph schemas, Neo4j instances, requests, document process errors):

- **`db_backend=dynamodb`** (default): PynamoDB models, `@method_cache` caching, DynamoDB table auto-creation.
- **`db_backend=postgresql`**: SQLAlchemy models, Alembic migrations, partial unique indexes for the single-active invariant.

**Neo4j is required under both backends** — it is the knowledge-graph store, not
a swappable backend. See:
- [DUAL_BACKEND_CONFIG.md](docs/DUAL_BACKEND_CONFIG.md) — architecture and configuration details
- [POSTGRESQL_SETUP.md](docs/POSTGRESQL_SETUP.md) — PostgreSQL setup guide

A repository dispatch boundary at `models/repositories/` isolates all GraphQL
queries, mutations, and domain handlers from backend-specific persistence.
A static adoption guard test ensures the GraphQL layer never imports
`models.dynamodb` or `models.postgresql` directly.

## Capabilities

- Extraction via `executeExtract` mutation or `dispatch_extract`
- Search modes:
  - `vector`
  - `text2cypher`
  - `vector_cypher`
  - `hybrid`
- RAG over tenant-scoped graph retrieval
- Active-only schema pattern per partition
- Active-only Neo4j instance pattern per partition
- Dual-backend metadata persistence (DynamoDB or PostgreSQL):
  - documents
  - graph schemas
  - Neo4j instances
  - requests
  - document process errors

## Repository Layout

```text
knowledge_graph_engine/
  handlers/
    extraction/         Extraction workflow and telemetry wrapper
    schema_resolution/  Active-schema resolution and evolution
    search/             Search and RAG handler implementations
    config.py           Shared runtime configuration (DB_BACKEND, db_session)
    neo4j_connection_manager.py
    partition_manager.py
  models/
    dynamodb/           PynamoDB models (5 entities + cache + utils + batch_loaders)
    postgresql/         SQLAlchemy models (5 entities + base + utils + batch_loaders)
    repositories/       Dispatch boundary (base, dispatch, dynamodb/, postgresql/)
  mutations/            GraphQL mutation entrypoints
  queries/              GraphQL query resolvers
  schema.py             GraphQL schema definition
  types/                GraphQL object types
  utils/                GraphRAG helpers, parsing, normalization
  main.py               Engine class, deploy(), dispatch_graphql(), dispatch_extract()
migration/
  alembic.ini           Alembic configuration
  alembic/              Migration environment (env.py, versions/)
```

## Configuration

Typical settings:

```python
settings = {
    "region_name": "us-east-1",
    "aws_access_key_id": "...",
    "aws_secret_access_key": "...",
    "initialize_tables": False,
    "llm_type": "openai",
    "llm_name": "gpt-4o",
    "openai_api_key": "...",
    "openai_base_url": None,
    "anthropic_api_key": "...",
    "anthropic_base_url": None,
    "ollama_host": "http://localhost:11434",
    "embedding_model": "text-embedding-3-small",
}
```

`partition_key` is never passed as a GraphQL mutation argument. It is derived from `endpoint_id` and `part_id` and attached through context.

## Notes

- `search_type` is no longer supported. Use `search_mode`.
- `daemon()` on `KnowledgeGraphEngine` is deprecated and now only logs a warning.
- `GraphRAGUtil` omits empty `base_url` values when constructing OpenAI/Anthropic clients.
- `text2cypher` can now consume examples stored on the active graph schema record.

## Testing

Run the test suite with:

```bash
pytest -q knowledge_graph_engine/tests
```

Dual-backend tests (no external services needed):

```bash
# Repository adoption guard — GraphQL layer uses dispatch boundary
pytest knowledge_graph_engine/tests/test_repository_adoption_guard.py -v

# Backend-agnostic dispatch — all 5 entities resolve on both backends
pytest knowledge_graph_engine/tests/test_backend_agnostic_dispatch.py -v

# Loader dispatch — DynamoDB and PostgreSQL loaders
pytest knowledge_graph_engine/tests/test_dual_backend_loaders.py -v

# Business flow parity — contract surface, single-active, cache config
pytest knowledge_graph_engine/tests/test_business_flow_parity.py -v
```

For a quick smoke pass around the recent refactor:

```bash
pytest knowledge_graph_engine/tests/test_import.py knowledge_graph_engine/tests/test_module_hardening.py -q
```
