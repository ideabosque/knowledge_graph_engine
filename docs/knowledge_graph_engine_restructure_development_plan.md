# Knowledge Graph Engine Restructure Status

**Reviewed:** 2026-06-15  
**Gateway package:** `silvaengine_gateway`  
**Core package:** `knowledge_graph_engine`

## Outcome

The transport split described by the original development plan is now
substantially implemented:

- `knowledge_graph_engine` owns graph business logic and exposes module-level
  `dispatch_graphql()` and `dispatch_extract()` functions.
- `silvaengine_gateway` owns FastAPI startup, authentication, rate limiting,
  route-manifest loading, dispatch execution, and background task polling.
- `python -m silvaengine_gateway` is the active daemon entry point.
- The default manifest registers KGE GraphQL, extraction submission, and
  extraction-status routes.

This document records the verified gateway state and remaining release work. It
is no longer a speculative file-move plan.

## Implemented Architecture

```text
HTTP client
    |
    v
silvaengine_gateway
    |-- FlexJWTMiddleware (local JWT or Cognito)
    |-- RateLimitMiddleware (per-process, per-IP)
    |-- routes.yaml / environment manifest
    |-- router_builder.py
    |     |-- synchronous dispatch in a thread pool
    |     `-- background dispatch with task-state updates
    |
    `--> knowledge_graph_engine.main dispatch functions
             |
             `--> DynamoDB / Neo4j / model providers
```

The gateway builds `partition_key` as `<endpoint_id>#<Part-Id>` and supplies it
both at the dispatch top level and in `context`. This matches the current KGE
GraphQL and extraction entry-point requirements.

## Implemented Gateway Surface

| Area | Current implementation |
|---|---|
| App factory | `silvaengine_gateway.app:create_app` |
| CLI/module entry point | `python -m silvaengine_gateway` |
| Authentication | Local JWT and Cognito JWT |
| Login | `POST /auth/token` using OAuth2 form data |
| Health | `GET /health` |
| Claims | `GET /me` |
| Dynamic routing | `ModuleSpec` and `RouteSpec` manifest models |
| KGE GraphQL | `knowledge_graph_engine.main:dispatch_graphql` |
| KGE extraction | `knowledge_graph_engine.main:dispatch_extract` |
| Task state | Pluggable `TaskBackend`; in-memory default |
| Rate limiting | In-memory per-IP window |

## Manifest Contract

Each module declares `name`, `package`, `transport`, and `routes`. Each route
declares:

| Field | Required | Notes |
|---|---:|---|
| `path` | Yes | FastAPI path template |
| `handler_type` | No | `graphql`, `rest`, `background`, or `task_status` |
| `dispatch` | Usually | Required except for `task_status` |
| `methods` | No | Defaults to `POST` |
| `auth` | No | Defaults to `true` |
| `name` | No | Optional FastAPI route name |

The current implementation uses direct core dispatch imports. The earlier
`adapter` and `background: true` manifest fields are obsolete.

## Verification

The repository test suite covers:

- App creation and public health behavior
- Authentication enforcement and local JWT lifecycle
- Manifest model validation and dispatch resolution
- Default route registration
- GraphQL request routing
- Extraction submission and task-status lookup

External DynamoDB, Neo4j, Cognito, and model-provider behavior remains
environment-dependent and requires deployment smoke testing.

## Remaining Release Work

1. Restrict manifest dispatch imports to approved package prefixes and fail
   startup on invalid or duplicate route/method registrations.
2. Add a production shared task backend with tenant ownership, retention, and
   cross-replica polling tests.
3. Add bounded background queues, timeouts, cancellation, and shutdown handling.
4. Avoid logging generated administrator tokens.
5. Validate Cognito configuration at startup and map provider failures to stable
   authentication responses.
6. Define an external multi-worker launch strategy; the module entry point
   currently starts one Uvicorn process.
7. Run container and live-service smoke tests with version-pinned KGE artifacts.

## Release Gate

The gateway is ready for a production release only after:

- Unit and integration tests pass in a clean environment.
- Custom manifests cannot import arbitrary modules.
- Task status survives the selected deployment topology.
- Authentication secrets and tokens are not emitted to logs.
- KGE GraphQL and extraction routes pass live DynamoDB/Neo4j smoke tests.
- The packaged wheel includes `routes.yaml` and starts without editable-install
  assumptions.
