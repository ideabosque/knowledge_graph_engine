# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import threading
from typing import Any, Dict

from .._compat import ensure_neo4j_compat

ensure_neo4j_compat()

from neo4j import GraphDatabase


class Neo4jConnectionManager:
    """
    Manages Neo4j driver instances, one per tenant.
    Drivers are cached and reused across requests.
    Thread-safe singleton pattern.
    """

    _drivers: Dict[str, Any] = {}
    _lock = threading.RLock()

    @classmethod
    def get_driver(cls, partition_key: str) -> Any:
        """Get or create a Neo4j driver for a specific tenant."""
        with cls._lock:
            if partition_key not in cls._drivers:
                instance = cls._load_instance(partition_key)
                cls._drivers[partition_key] = GraphDatabase.driver(
                    instance["neo4j_uri"],
                    auth=(instance["neo4j_username"], instance["neo4j_password"]),
                    max_connection_pool_size=instance.get("max_connection_pool_size", 5),
                )
            return cls._drivers[partition_key]

    @classmethod
    def _load_instance(cls, partition_key: str) -> Any:
        """Load the active Neo4j instance for a partition.

        Uses the repository dispatch boundary so both DynamoDB and PostgreSQL
        backends are supported.
        """
        from ..models.repositories import get_repo

        repo = get_repo("neo4j_instance")
        instance = repo.resolve_active(partition_key)
        if instance is None:
            raise ValueError(
                f"No active Neo4j instance for partition: {partition_key}. "
                f"Register via insertUpdateNeo4jInstance mutation first."
            )
        return instance

    @classmethod
    def close_driver(cls, partition_key: str) -> None:
        """Close and remove a tenant's driver (e.g., on decommission)."""
        from .config import Config

        with cls._lock:
            driver = cls._drivers.pop(partition_key, None)
            if driver:
                driver.close()
        Config.clear_graph_rag_util(partition_key)

    @classmethod
    def close_all(cls) -> None:
        """Graceful shutdown: close all drivers."""
        from .config import Config

        with cls._lock:
            partition_keys = list(cls._drivers.keys())
            for driver in cls._drivers.values():
                driver.close()
            cls._drivers.clear()
        for pk in partition_keys:
            Config.clear_graph_rag_util(pk)
