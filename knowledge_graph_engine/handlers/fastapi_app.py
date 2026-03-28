# -*- coding: utf-8 -*-
from __future__ import annotations, print_function

__author__ = "silvaengine"

import asyncio
import os
import time
import traceback
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Dict, Tuple

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import Config

# === Rate Limiting ===
_request_counts = defaultdict(list)

# === Background extraction state ===
_extract_tasks: Dict[str, Dict[str, Any]] = {}
_extract_max_workers = int(os.environ.get("KGE_EXTRACT_WORKERS", "4"))
_extract_executor = ThreadPoolExecutor(max_workers=_extract_max_workers, thread_name_prefix="kg-extract")


def _get_partition_key(endpoint_id: str, request: Request) -> Tuple[str, str | None]:
    """Construct partition_key from endpoint_id and optional Part-Id header."""
    part_id = request.headers.get("Part-Id") or request.headers.get("Part-ID")
    if part_id:
        return f"{endpoint_id}#{part_id}", part_id
    return endpoint_id, None


def _rate_limit_check(
    client_ip: str, max_requests: int = 100, window_seconds: int = 60
):
    now = time.time()
    _request_counts[client_ip] = [
        t for t in _request_counts[client_ip] if now - t < window_seconds
    ]
    if len(_request_counts[client_ip]) >= max_requests:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _request_counts[client_ip].append(now)


def _current_user(request: Request) -> Dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# === Application Lifecycle ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    if Config.get_logger():
        Config.get_logger().info("Starting Knowledge Graph Engine FastAPI server...")
    yield
    if Config.get_logger():
        Config.get_logger().info("Shutting down Knowledge Graph Engine FastAPI server...")
    _extract_executor.shutdown(wait=False)
    if Config.auth_provider == "cognito":
        try:
            from .jwt_cognito import cleanup_http_client

            await cleanup_http_client()
        except Exception:
            pass


# === FastAPI App ===
app = FastAPI(
    title="Knowledge Graph Engine API",
    description="GraphQL API for knowledge graph extraction, search, and RAG queries.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# === Health Check (public) ===
@app.get("/health")
def health():
    return {"status": "ok", "service": "knowledge-graph-engine"}


# === Current User ===
@app.get("/me")
def me(user: Dict = Depends(_current_user)) -> Dict:
    return user


# === GraphQL Endpoint ===
@app.post("/{endpoint_id}/knowledge_graph_engine_graphql")
async def knowledge_graph_engine_graphql(endpoint_id: str, request: Request) -> Dict:
    """Handle GraphQL queries and mutations for the Knowledge Graph Engine."""
    _rate_limit_check(request.client.host if request.client else "unknown")

    params = await request.json()
    partition_key, part_id = _get_partition_key(endpoint_id, request)

    if not params.get("context"):
        params["context"] = {}

    params["context"]["partition_key"] = partition_key
    params["context"]["part_id"] = part_id
    params["endpoint_id"] = endpoint_id
    params["part_id"] = part_id

    # Run sync GraphQL execution in thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        _extract_executor,
        lambda: Config.kge.knowledge_graph_engine_graphql(**params),
    )

    try:
        from silvaengine_utility.serializer import Serializer
        result = Serializer.json_loads(response.get("body", response))
    except (ImportError, AttributeError):
        import json
        body = response.get("body", response)
        result = json.loads(body) if isinstance(body, str) else body

    return result


# === Async Extract Endpoint (background processing) ===
@app.post("/{endpoint_id}/extract")
async def extract_async(endpoint_id: str, request: Request) -> Dict:
    """
    Submit an extraction job that runs in the background.
    Returns immediately with a task_id for polling.

    Request body:
        {
            "text": "...",
            "graph_schema": {...} | null,
            "document_source": "woocommerce",
            "document_external_id": "product-123"
        }
    """
    _rate_limit_check(request.client.host if request.client else "unknown")

    params = await request.json()
    partition_key, part_id = _get_partition_key(endpoint_id, request)
    text = params.get("text")

    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    task_id = f"task-{uuid.uuid4().hex[:12]}"

    _extract_tasks[task_id] = {
        "status": "pending",
        "created_at": time.time(),
        "partition_key": partition_key,
        "document_external_id": params.get("document_external_id"),
        "result": None,
        "error": None,
    }

    # Run extraction in background thread
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _extract_executor,
        _run_extract_background,
        task_id,
        endpoint_id,
        part_id,
        partition_key,
        params,
    )

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Extraction job submitted. Poll GET /{endpoint_id}/extract/{task_id} for status.",
    }


@app.get("/{endpoint_id}/extract/{task_id}")
async def extract_status(endpoint_id: str, task_id: str) -> Dict:
    """Check the status of a background extraction job."""
    task = _extract_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    response = {
        "task_id": task_id,
        "status": task["status"],
        "partition_key": task["partition_key"],
        "document_external_id": task.get("document_external_id"),
    }

    if task["status"] == "completed":
        response["result"] = task["result"]
        # Clean up after retrieval
        _extract_tasks.pop(task_id, None)
    elif task["status"] == "failed":
        response["error"] = task["error"]
        _extract_tasks.pop(task_id, None)
    elif task["status"] == "pending":
        elapsed = time.time() - task["created_at"]
        response["elapsed_seconds"] = round(elapsed, 1)

    return response


def _run_extract_background(
    task_id: str,
    endpoint_id: str,
    part_id: str,
    partition_key: str,
    params: Dict[str, Any],
) -> None:
    """Execute extraction in a background thread."""
    logger = Config.get_logger()
    try:
        _extract_tasks[task_id]["status"] = "running"

        from ..utils.listener import create_listener_info
        from ..handlers.extractor import Extractor

        info = create_listener_info(
            logger,
            "extract",
            Config.get_setting(),
            endpoint_id=endpoint_id,
            part_id=part_id,
            partition_key=partition_key,
        )

        extractor = Extractor(info)
        result = extractor.extract(
            partition_key=partition_key,
            text=params.get("text", ""),
            graph_schema=params.get("graph_schema"),
            document_source=params.get("document_source", "unknown"),
            document_external_id=params.get("document_external_id"),
        )

        _extract_tasks[task_id]["status"] = "completed"
        _extract_tasks[task_id]["result"] = result

        if logger:
            logger.info(
                f"Background extraction completed: task={task_id}, "
                f"doc={result.get('document_uuid')}, "
                f"entities={result.get('entities_extracted', 0)}"
            )

    except Exception as e:
        _extract_tasks[task_id]["status"] = "failed"
        _extract_tasks[task_id]["error"] = str(e)
        if logger:
            logger.error(f"Background extraction failed: task={task_id}, error={traceback.format_exc()}")
