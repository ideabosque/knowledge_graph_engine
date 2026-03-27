# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Tuple


class PartitionManager:
    """
    Manages partition_key construction/parsing for multi-tenant isolation.
    Each partition_key maps to a dedicated Neo4j Community instance.
    """

    @staticmethod
    def build_partition_key(endpoint_id: str, part_id: str) -> str:
        """Concatenate endpoint_id and part_id into partition_key."""
        return f"{endpoint_id}#{part_id}"

    @staticmethod
    def parse_partition_key(partition_key: str) -> Tuple[str, str]:
        """Extract endpoint_id and part_id from partition_key."""
        endpoint_id, part_id = partition_key.split("#", 1)
        return endpoint_id, part_id