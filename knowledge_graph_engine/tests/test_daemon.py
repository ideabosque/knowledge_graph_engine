# -*- coding: utf-8 -*-
"""
Daemon launch tests for Knowledge Graph Engine.
Launches daemon() in a background thread and tests endpoints with real HTTP requests.

Run with: pytest tests/test_daemon.py -m integration -v
"""
from __future__ import print_function

__author__ = "silvaengine"

import threading
import time

import pytest
import requests

from .conftest import SETTING, logger


@pytest.fixture(scope="module")
def daemon_server():
    """Launch engine.daemon() in a background thread and yield the base URL."""
    from knowledge_graph_engine.main import KnowledgeGraphEngine

    port = 18999
    setting = {
        **SETTING,
        "auth_provider": "local",
        "jwt_secret_key": "test-daemon-secret",
        "jwt_algorithm": "HS256",
        "access_token_exp": "15",
        "admin_username": "admin",
        "admin_password": "admin",
        "admin_static_token": "",
        "port": port,
    }

    engine = KnowledgeGraphEngine(logger, **setting)

    thread = threading.Thread(target=engine.daemon, daemon=True)
    thread.start()

    # Wait for server to be ready
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        try:
            resp = requests.get(f"{base_url}/health", timeout=1)
            if resp.status_code == 200:
                break
        except requests.ConnectionError:
            time.sleep(0.5)
    else:
        pytest.fail("Daemon server did not start within 15 seconds")

    yield base_url


@pytest.fixture(scope="module")
def auth_token(daemon_server):
    """Obtain a JWT token from the running daemon."""
    resp = requests.post(
        f"{daemon_server}/auth/token",
        data={"username": "admin", "password": "admin"},
    )
    assert resp.status_code == 200, f"Auth failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.mark.integration
class TestDaemonHealth:
    def test_health(self, daemon_server):
        resp = requests.get(f"{daemon_server}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "knowledge-graph-engine"


@pytest.mark.integration
class TestDaemonAuth:
    def test_login(self, daemon_server):
        resp = requests.post(
            f"{daemon_server}/auth/token",
            data={"username": "admin", "password": "admin"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_invalid(self, daemon_server):
        resp = requests.post(
            f"{daemon_server}/auth/token",
            data={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_unauthenticated(self, daemon_server):
        resp = requests.get(f"{daemon_server}/me")
        assert resp.status_code == 401

    def test_me(self, daemon_server, auth_token):
        resp = requests.get(
            f"{daemon_server}/me",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"


@pytest.mark.integration
class TestDaemonGraphQL:
    def test_ping(self, daemon_server, auth_token):
        endpoint_id = SETTING.get("endpoint_id", "gpt")
        resp = requests.post(
            f"{daemon_server}/{endpoint_id}/knowledge_graph_graphql",
            json={"query": "{ ping }"},
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Part-Id": SETTING.get("part_id", ""),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["ping"].startswith("Hello at ")

    def test_graphql_unauthenticated(self, daemon_server):
        endpoint_id = SETTING.get("endpoint_id", "gpt")
        resp = requests.post(
            f"{daemon_server}/{endpoint_id}/knowledge_graph_graphql",
            json={"query": "{ ping }"},
        )
        assert resp.status_code == 401

    def test_neo4j_instance_query(self, daemon_server, auth_token):
        endpoint_id = SETTING.get("endpoint_id", "gpt")
        query = """
            query($instanceId: String!) {
                neo4jInstance(instanceId: $instanceId) {
                    partitionKey
                    instanceId
                    neo4jUri
                    status
                }
            }
        """
        resp = requests.post(
            f"{daemon_server}/{endpoint_id}/knowledge_graph_graphql",
            json={"query": query, "variables": {"instanceId": "default"}},
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Part-Id": SETTING.get("part_id", ""),
            },
        )
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_vector_search(self, daemon_server, auth_token):
        endpoint_id = SETTING.get("endpoint_id", "gpt")
        query = """
            query($queryText: String!, $searchMode: String, $topK: Int) {
                search(queryText: $queryText, searchMode: $searchMode, topK: $topK) {
                    total
                    results
                }
            }
        """
        resp = requests.post(
            f"{daemon_server}/{endpoint_id}/knowledge_graph_graphql",
            json={
                "query": query,
                "variables": {
                    "queryText": "test search",
                    "searchMode": "vector",
                    "topK": 2,
                },
            },
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Part-Id": SETTING.get("part_id", ""),
            },
        )
        assert resp.status_code == 200
        assert "data" in resp.json()
