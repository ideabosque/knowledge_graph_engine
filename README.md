# Knowledge Graph Engine

`knowledge_graph_engine` is a multi-tenant SilvaEngine module for extracting entities and relationships from text, storing them in tenant-isolated Neo4j instances, and exposing retrieval flows through GraphQL.

## Current State

The module already provides:

- Partition-aware request handling through `partition_key = "{endpoint_id}#{part_id}"`.
- A GraphQL engine entrypoint and deploy metadata.
- Dedicated Neo4j driver routing per tenant via `Neo4jConnectionManager`.
- Schema resolution in three modes: auto-generated, user-provided, and hybrid extension.
- Extraction, search, and RAG handlers wired around GraphRAG-style utilities.
- DynamoDB-backed model scaffolding for documents, schemas, data sources, requests, and Neo4j instances.
- Basic unit coverage for helpers, partitioning, search wiring, extraction wiring, and compatibility behavior.

The module is functional as a foundation, but it is not fully production-complete yet. The biggest remaining work is around infrastructure lifecycle, integration coverage, and tightening the contract between the GraphQL schema and the persistence layer.

## Architecture

The engine follows a tenant-first execution path:

1. Request parameters are normalized into `endpoint_id`, `part_id`, and `partition_key`.
2. The partition is used to resolve a dedicated Neo4j connection from the registry model.
3. Schema resolution chooses a saved schema, a generated schema, or a merged hybrid schema.
4. Extraction writes graph data and embeddings into the tenant's Neo4j instance.
5. Search and RAG operate only against that tenant's schema and indexes.

This design keeps data isolation simple: one partition routes to one Neo4j instance.

## Module Layout

```text
knowledge_graph_engine/
  handlers/      Request orchestration, routing, extraction, search, RAG
  models/        DynamoDB models and supporting loaders
  mutations/     GraphQL mutation entrypoints
  queries/       GraphQL query resolvers
  types/         GraphQL object types
  utils/         Parsing, normalization, listeners, GraphRAG helpers
  main.py        Engine entrypoint and deploy metadata
  schema.py      GraphQL schema definition
```

## Usage

### Python

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
        results { text score }
        total
      }
    }
    """,
    variables={"queryText": "What does Acme build?"},
)
```

### Search Modes

The search layer accepts `search_mode` and also supports the legacy alias `search_type`.

Supported values:

- `vector`
- `text2cypher`
- `vector_cypher`
- `hybrid`

### Extraction Contract

`Extractor.extract()` now requires an explicit `partition_key` argument. That makes the handler safer to call directly and avoids hidden behavior between synchronous and asynchronous entrypoints.

## Configuration

Relevant settings used by the current implementation:

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

## Development Notes

- The package now uses lazy top-level imports so helper modules can be imported without forcing the full runtime dependency stack.
- A lightweight compatibility layer allows the package and unit tests to run in minimal environments where optional graph dependencies are not installed.
- The GraphQL search and RAG resolvers normalize `search_type` into `search_mode` to preserve backward compatibility.

## Testing

Run the project tests with:

```bash
pytest -q tests
```

If the workspace contains locked `pytest-cache-files-*` directories, scope pytest to `tests/` explicitly to avoid collection errors.
