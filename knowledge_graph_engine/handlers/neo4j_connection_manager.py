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
                    instance.neo4j_uri,
                    auth=(instance.neo4j_username, instance.neo4j_password),
                    max_connection_pool_size=instance.max_connection_pool_size,
                )
            return cls._drivers[partition_key]

    @classmethod
    def _load_instance(cls, partition_key: str) -> Any:
        """Load the active Neo4j instance for a partition."""
        from ..models.neo4j_instance import get_active_neo4j_instance, Neo4jInstanceModel

        try:
            return get_active_neo4j_instance(partition_key)
        except Neo4jInstanceModel.DoesNotExist:
            raise ValueError(
                f"No active Neo4j instance for partition: {partition_key}. "
                f"Register via insertUpdateNeo4jInstance mutation first."
            )

    @classmethod
    def close_driver(cls, partition_key: str) -> None:
        """Close and remove a tenant's driver (e.g., on decommission)."""
        with cls._lock:
            driver = cls._drivers.pop(partition_key, None)
            if driver:
                driver.close()

    @classmethod
    def close_all(cls) -> None:
        """Graceful shutdown: close all drivers."""
        with cls._lock:
            for driver in cls._drivers.values():
                driver.close()
            cls._drivers.clear()
