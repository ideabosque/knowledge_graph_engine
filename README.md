# Knowledge Graph Engine

`knowledge_graph_engine` is a multi-tenant SilvaEngine module for extracting entities and relationships from text, storing them in tenant-isolated Neo4j instances, and exposing retrieval flows through GraphQL.

## Current State

The module provides:

- Partition-aware request handling through `partition_key = "{endpoint_id}#{part_id}"`.
- A GraphQL engine entrypoint, deploy metadata, and a **FastAPI daemon mode** (`engine.daemon()`).
- Dedicated Neo4j driver routing per tenant via `Neo4jConnectionManager` using the **active Neo4j instance**.
- **Active-only schema pattern**: one active schema per partition, automatically used by extract, search, and RAG.
- **Active-only instance pattern**: one active Neo4j instance per partition, auto-deactivation on insert/activate.
- Schema resolution: active schema, user-provided dict (saved as new active), auto-generated, or hybrid extension.
- Extraction, search (4 modes), and RAG handlers wired around GraphRAG-style utilities.
- DynamoDB-backed models for documents, schemas, data sources, requests, and Neo4j instances.
- JWT authentication middleware for daemon mode (local users + Cognito).
- `partition_key` passed exclusively via context — never as a client argument in mutations.

## Architecture

The engine follows a tenant-first execution path:

1. Request parameters are normalized into `endpoint_id`, `part_id`, and `partition_key`.
2. The partition resolves the **active Neo4j instance** from the registry model.
3. Schema resolution uses the **active schema** for the partition (or a user-provided dict which becomes the new active).
4. Extraction writes graph data and embeddings into the tenant's Neo4j instance.
5. Search and RAG operate only against that tenant's active schema and indexes.

This design keeps data isolation simple: one partition routes to one active Neo4j instance and one active schema.

## Module Layout

```text
knowledge_graph_engine/
  handlers/      Request orchestration, routing, extraction, search, RAG, auth, GraphQL schema
  models/        DynamoDB models and supporting loaders
  mutations/     GraphQL mutation entrypoints
  queries/       GraphQL query resolvers
  types/         GraphQL object types
  utils/         Parsing, normalization, listeners, GraphRAG helpers
  main.py        Engine class + daemon() + deploy() + main()
  __main__.py    python -m entry point
```

## Usage

### GraphQL Mode (SilvaEngine)

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

result = engine.knowledge_graph_engine_graphql(
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

### Daemon Mode (FastAPI)

Start a standalone FastAPI server with JWT authentication:

```python
from knowledge_graph_engine.main import main
main()  # Reads settings from environment variables
```

Or via CLI:

```bash
python -m knowledge_graph_engine
```

The daemon exposes:
- `POST /{endpoint_id}/knowledge_graph_engine_graphql` — GraphQL endpoint (requires JWT token, `Part-Id` header)
- `POST /auth/token` — Get JWT token (`username` + `password` form data)
- `GET /me` — Current user info (requires JWT token)
- `GET /health` — Health check (no auth required)

### Search Modes

The search layer accepts `search_mode` and also supports the legacy alias `search_type`.

Supported values:

- `vector`
- `text2cypher`
- `vector_cypher`
- `hybrid`

### Extraction Contract

`Extractor.extract()` requires an explicit `partition_key` argument. The active schema for the partition is used automatically. If a `graph_schema` dict is provided, it becomes the new active schema (the old active one is deactivated).

### Active-Only Pattern

Only one Neo4j instance and one graph schema can be active per partition at any time:

- **Neo4j Instance**: `get_active_neo4j_instance(partition_key)` returns the active instance. When a new instance is inserted (or an existing one is activated), the previous active instance is automatically deactivated. The cached Neo4j driver is also closed so the new instance is picked up.
- **Graph Schema**: `get_active_graph_schema(partition_key)` returns the active schema. Same auto-deactivation behavior. Extract, search, and RAG all use the active schema — `schema_name` is not exposed as a parameter in these operations.
- **Schema CRUD**: Use `insertUpdateGraphSchema` / `deleteGraphSchema` mutations to manage multiple schemas. The `schema_name` field is only used as the DynamoDB range key for CRUD operations.

## Configuration

### Core Settings

```python
settings = {
    "region_name": "us-east-1",
    "aws_access_key_id": "...",
    "aws_secret_access_key": "...",
    "initialize_tables": False,
    "llm_type": "openai",
    "llm_name": "gpt-4o",
    "openai_api_key": "...",
    "anthropic_api_key": "...",
    "ollama_host": "http://localhost:11434",
    "embedding_model": "text-embedding-3-small",
}
```

### Daemon Mode Settings (environment variables)

```bash
# Server
PORT=8000

# Auth
AUTH_PROVIDER=local              # "local" or "cognito"
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXP=30              # minutes

# Local auth
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
LOCAL_USER_FILE=/path/to/users.json

# Cognito auth (when AUTH_PROVIDER=cognito)
# COGNITO_USER_POOL_ID=...
# COGNITO_CLIENT_ID=...
# COGNITO_REGION=...
```

## Development Notes

- The package uses lazy top-level imports so helper modules can be imported without forcing the full runtime dependency stack.
- A lightweight compatibility layer allows the package and unit tests to run in minimal environments where optional graph dependencies are not installed.
- The GraphQL search and RAG resolvers normalize `search_type` into `search_mode` to preserve backward compatibility.
- `partition_key` is never accepted as a client argument in mutations — it is always derived from `info.context`.
- `schema_name` is not exposed in extract, search, or RAG operations — the active schema is always used.
- When a `graph_schema` dict is provided in `executeExtract`, it is saved as the new active schema (deactivating the old one).
- The `daemon()` method follows the `ai_mcp_daemon_engine` pattern: starts uvicorn with JWT middleware and auth router.

## Testing

Run the project tests with:

```bash
pytest -q tests
```

If the workspace contains locked `pytest-cache-files-*` directories, scope pytest to `tests/` explicitly to avoid collection errors.
