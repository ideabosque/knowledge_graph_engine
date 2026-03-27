# -*- coding: utf-8 -*-
from __future__ import annotations, print_function

__author__ = "silvaengine"

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, Dict, Tuple

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from silvaengine_utility.serializer import Serializer

from .config import Config

# === Rate Limiting ===
_request_counts = defaultdict(list)


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

    response = Config.kge.knowledge_graph_engine_graphql(**params)
    result = Serializer.json_loads(response.get("body", response))

    return result


