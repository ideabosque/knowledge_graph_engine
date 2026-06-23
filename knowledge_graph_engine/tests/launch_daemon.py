#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Launch the Knowledge Graph Engine daemon for manual testing (e.g. Postman).

Usage:
    python tests/launch_daemon.py
    # Server starts at http://localhost:8000

    # Then in Postman:
    # 1. POST http://localhost:8000/auth/token  (form-data: username=admin, password=admin)
    # 2. Use the returned access_token as Bearer token for other requests
"""
from __future__ import print_function

import logging
import os
import sys

from dotenv import load_dotenv

# Load .env from tests directory
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("knowledge_graph_engine")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from knowledge_graph_engine.main import KnowledgeGraphEngine

engine = KnowledgeGraphEngine(
    logger,
    **{
        # AWS
        "region_name": os.getenv("region_name"),
        "aws_access_key_id": os.getenv("aws_access_key_id"),
        "aws_secret_access_key": os.getenv("aws_secret_access_key"),
        # Tenant
        "endpoint_id": os.getenv("endpoint_id"),
        "part_id": os.getenv("part_id"),
        # Tables
        "initialize_tables": int(os.getenv("initialize_tables", "0")),
        "cache_enabled": int(os.getenv("cache_enabled", "0")),
        # LLM
        "llm_type": os.getenv("llm_type", "openai"),
        "llm_name": os.getenv("llm_name", "gpt-4o"),
        "openai_api_key": os.getenv("openai_api_key"),
        "openai_base_url": os.getenv("openai_base_url"),
        "anthropic_api_key": os.getenv("anthropic_api_key"),
        "anthropic_base_url": os.getenv("anthropic_base_url"),
        "ollama_host": os.getenv("ollama_host", "http://localhost:11434"),
        "mistralai_api_key": os.getenv("mistralai_api_key"),
        "vertexai_system_instruction": os.getenv("vertexai_system_instruction"),
        # Embeddings
        "embedding_provider": os.getenv("embedding_provider"),
        "embedding_model": os.getenv("embedding_model", "text-embedding-3-small"),
        # Neo4j
        "neo4j_uri": os.getenv("neo4j_uri", "bolt://localhost:7687"),
        "neo4j_username": os.getenv("neo4j_username", "neo4j"),
        "neo4j_password": os.getenv("neo4j_password"),
        "neo4j_database": os.getenv("neo4j_database", "neo4j"),
        # Auth
        "auth_provider": os.getenv("AUTH_PROVIDER", "local"),
        "jwt_secret_key": os.getenv("JWT_SECRET_KEY", "CHANGEME"),
        "jwt_algorithm": os.getenv("JWT_ALGORITHM", "HS256"),
        "access_token_exp": os.getenv("ACCESS_TOKEN_EXP", "15"),
        "admin_username": os.getenv("ADMIN_USERNAME", "admin"),
        "admin_password": os.getenv("ADMIN_PASSWORD", "admin"),
        "admin_static_token": os.getenv("ADMIN_STATIC_TOKEN", ""),
        "local_user_file": os.getenv("LOCAL_USER_FILE"),
        # Cognito
        "cognito_user_pool_id": os.getenv("COGNITO_USER_POOL_ID", ""),
        "cognito_app_client_id": os.getenv("COGNITO_APP_CLIENT_ID", ""),
        "cognito_app_secret": os.getenv("COGNITO_APP_SECRET", ""),
        "cognito_jwks_url": os.getenv("COGNITO_JWKS_URL"),
        # Server
        "port": int(os.getenv("PORT", "8000")),
    },
)
engine.daemon()
