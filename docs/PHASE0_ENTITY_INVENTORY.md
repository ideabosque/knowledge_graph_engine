# Phase 0 Entity Inventory — Dual-Backend Field Mapping

> Verified against source on 2026-06-21.
> Covers the 5 metadata entities. Neo4j graph store is out of scope.

## 1. Document (`kge-documents` → `documents`)

| Field | DynamoDB Type | PostgreSQL Column | Notes |
| --- | --- | --- | --- |
| `partition_key` | UnicodeAttribute (hash) | String(128), PK | Tenant key |
| `document_uuid` | UnicodeAttribute (range) | String, PK | Not UUID-typed in DDB (e.g. `doc-...`) |
| `endpoint_id` | UnicodeAttribute(null) | String(64) | |
| `part_id` | UnicodeAttribute(null) | String(64) | |
| `document_source` | UnicodeAttribute | String | Required |
| `document_external_id` | UnicodeAttribute(null) | String | LSI range in DDB |
| `chunk_index` | NumberAttribute(default=0) | Integer | |
| `document_title` | UnicodeAttribute(null) | String | |
| `content` | UnicodeAttribute(null) | Text | |
| `content_embedding` | ListAttribute(null) | JSONB | List of floats; vector search in Neo4j |
| `status` | UnicodeAttribute(default="active") | String | |
| `updated_by` | UnicodeAttribute(null) | String | |
| `created_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | |
| `updated_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | LSI range in DDB |

Indexes: `(partition_key, updated_at)`, `(partition_key, document_external_id)`, `(partition_key, status)`

## 2. GraphSchema (`kge-graph_schemas` → `graph_schemas`)

| Field | DynamoDB Type | PostgreSQL Column | Notes |
| --- | --- | --- | --- |
| `partition_key` | UnicodeAttribute (hash) | String(128), PK | |
| `schema_name` | UnicodeAttribute (range) | String, PK | Natural key (not UUID) |
| `endpoint_id` | UnicodeAttribute(null) | String(64) | |
| `part_id` | UnicodeAttribute(null) | String(64) | |
| `schema_type` | UnicodeAttribute | String | Default "auto" |
| `schema_definition` | MapAttribute | JSONB | |
| `source_text_hash` | UnicodeAttribute(null) | String | |
| `neo4j_schema_string` | UnicodeAttribute(null) | Text | |
| `text2cypher_examples` | UnicodeAttribute(null) | JSONB | Promote from JSON string to JSONB |
| `status` | UnicodeAttribute(default="active") | String | Single-active invariant |
| `updated_by` | UnicodeAttribute(null) | String | |
| `created_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | |
| `updated_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | LSI range |

Indexes: `(partition_key, updated_at)`, `(partition_key, status)` + partial unique index `WHERE status = 'active'`

## 3. Neo4jInstance (`kge-neo4j_instances` → `neo4j_instances`)

| Field | DynamoDB Type | PostgreSQL Column | Notes |
| --- | --- | --- | --- |
| `partition_key` | UnicodeAttribute (hash) | String(128), PK | |
| `instance_id` | UnicodeAttribute (range) | String, PK | Natural key (e.g. "default") |
| `endpoint_id` | UnicodeAttribute(null) | String(64) | |
| `part_id` | UnicodeAttribute(null) | String(64) | |
| `neo4j_uri` | UnicodeAttribute | String | Required |
| `neo4j_username` | UnicodeAttribute(default="neo4j") | String | |
| `neo4j_password` | UnicodeAttribute | String | Required |
| `neo4j_database` | UnicodeAttribute(default="neo4j") | String | |
| `container_id` | UnicodeAttribute(null) | String | |
| `status` | UnicodeAttribute(default="active") | String | Single-active invariant |
| `max_connection_pool_size` | NumberAttribute(default=5) | Integer | |
| `created_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | |
| `updated_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | |

Indexes: `(partition_key, status)` + partial unique index `WHERE status = 'active'`

## 4. Request (`kge-requests` → `requests`)

| Field | DynamoDB Type | PostgreSQL Column | Notes |
| --- | --- | --- | --- |
| `partition_key` | UnicodeAttribute (hash) | String(128), PK | |
| `request_uuid` | UnicodeAttribute (range) | String, PK | Not UUID-typed (e.g. `req-...`) |
| `endpoint_id` | UnicodeAttribute(null) | String(64) | |
| `part_id` | UnicodeAttribute(null) | String(64) | |
| `user_query` | UnicodeAttribute(null) | Text | |
| `cypher_query` | UnicodeAttribute(null) | Text | |
| `search_mode` | UnicodeAttribute(default="text2cypher") | String | |
| `results` | ListAttribute(null) | JSONB | List of result dicts |
| `updated_by` | UnicodeAttribute(null) | String | |
| `created_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | |
| `updated_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | |

Indexes: `(partition_key, search_mode)`

## 5. DocumentProcessError (`kge-document_process_errors` → `document_process_errors`)

| Field | DynamoDB Type | PostgreSQL Column | Notes |
| --- | --- | --- | --- |
| `partition_key` | UnicodeAttribute (hash) | String(128), PK | |
| `process_error_uuid` | UnicodeAttribute (range) | String, PK | Not UUID-typed (e.g. `err-...`) |
| `document_source` | UnicodeAttribute | String | Required |
| `document_external_id` | UnicodeAttribute(null) | String | |
| `chunk_index` | NumberAttribute(null) | Integer | |
| `error_message` | UnicodeAttribute(null) | Text | |
| `process_status` | UnicodeAttribute(default="failed") | String | |
| `process_count` | NumberAttribute(default=0) | Integer | |
| `created_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | |
| `updated_at` | UTCDateTimeAttribute | TIMESTAMP(timezone=True) | |

No secondary indexes.

## AWS Services in PostgreSQL Mode

KGE uses `aws_lambda` for dispatch (the `Config.aws_lambda` client is always initialized
in the current code). In the dual-backend pattern, the AWS initialization stays unconditional
for both backends in KGE (unlike rfq_engine which makes AWS optional in PG mode) because:

1. `aws_lambda` is used by the core dispatch path (Lambda deployment fallback).
2. S3 may be used for file parsing in extraction handlers.
3. Even in PG mode, the engine may be deployed behind API Gateway → Lambda.

**Decision**: Keep `_initialize_aws_services` unconditional for both backends in KGE.
The `_initialize_dynamodb_meta` (PynamoDB `BaseModel.Meta` setup) is DynamoDB-only.

## Cache Config Reconciliation

- `document_process_error` IS absent from current `CACHE_ENTITY_CONFIG` but its model
  DOES have `@method_cache`. We will add it to the DynamoDB cache config.
- Two `list_resolver` paths point at `models.*` instead of `queries.*`:
  - `neo4j_instance` → `models.neo4j_instance.resolve_neo4j_instance_list`
  - `request` → `models.request.resolve_request_list`
  These will be updated to `models.dynamodb.*` paths in Phase 1.
- PostgreSQL repositories will NOT use `@method_cache` (same as rfq_engine). The PG cache
  config maps will be empty.