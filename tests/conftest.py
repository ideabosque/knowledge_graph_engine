# -*- coding: utf-8 -*-
"""
Pytest configuration and fixtures for Knowledge Graph Engine tests.
"""
from __future__ import print_function

import logging
import os
import sys
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from graphene import ResolveInfo

load_dotenv()

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("test_knowledge_graph_engine")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

SETTING = {
    "region_name": os.getenv("region_name"),
    "aws_access_key_id": os.getenv("aws_access_key_id"),
    "aws_secret_access_key": os.getenv("aws_secret_access_key"),
    "endpoint_id": os.getenv("endpoint_id"),
    "part_id": os.getenv("part_id"),
    "initialize_tables": int(os.getenv("initialize_tables", "0")),
    "cache_enabled": int(os.getenv("cache_enabled", "0")),
    "llm_type": os.getenv("llm_type", "openai"),
    "llm_name": os.getenv("llm_name", "gpt-4o"),
    "openai_api_key": os.getenv("openai_api_key"),
    "openai_base_url": os.getenv("openai_base_url"),
    "anthropic_api_key": os.getenv("anthropic_api_key"),
    "anthropic_base_url": os.getenv("anthropic_base_url"),
    "ollama_host": os.getenv("ollama_host", "http://localhost:11434"),
    "mistralai_api_key": os.getenv("mistralai_api_key"),
    "vertexai_system_instruction": os.getenv("vertexai_system_instruction"),
    "embedding_provider": os.getenv("embedding_provider"),
    "embedding_model": os.getenv("embedding_model", "text-embedding-3-small"),
    "neo4j_uri": os.getenv("neo4j_uri", "bolt://localhost:7687"),
    "neo4j_username": os.getenv("neo4j_username", "neo4j"),
    "neo4j_password": os.getenv("neo4j_password"),
    "neo4j_database": os.getenv("neo4j_database", "neo4j"),
}


@pytest.fixture(scope="function")
def mock_logger():
    logger = MagicMock(spec=logging.Logger)
    return logger


@pytest.fixture(scope="function")
def mock_info(mock_logger):
    info = MagicMock(spec=ResolveInfo)
    info.context = {
        "logger": mock_logger,
        "endpoint_id": "test-endpoint-001",
        "part_id": "test-part-001",
        "partition_key": "test-endpoint-001#test-part-001",
    }
    return info


@pytest.fixture(scope="function")
def partition_key():
    return "test-endpoint-001#test-part-001"


@pytest.fixture(scope="session")
def engine():
    """Create a KnowledgeGraphEngine instance with real settings for integration tests."""
    from knowledge_graph_engine.main import KnowledgeGraphEngine

    return KnowledgeGraphEngine(logger, **SETTING)


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: Unit tests (no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (DB, API)")
    config.addinivalue_line("markers", "extract: Knowledge graph extraction tests")
    config.addinivalue_line("markers", "search: Search and RAG tests")