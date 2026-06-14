# -*- coding: utf-8 -*-
"""Partition-key construction utilities."""

from __future__ import print_function

__author__ = "silvaengine"

from typing import Tuple


def build_partition_key(endpoint_id: str, part_id: str) -> Tuple[str, str]:
    """Construct partition_key from endpoint_id and part_id.

    Returns (partition_key, part_id) tuple.

    A bare endpoint_id would hash to its own partition bucket, hiding data
    written under the proper `endpoint#part_id` key — so we validate part_id
    is present rather than silently mis-routing.

    Raises:
        ValueError: If part_id is empty or missing.
    """
    if not part_id:
        raise ValueError(
            "part_id is required to construct partition_key. "
            "Got empty or None value."
        )
    return f"{endpoint_id}#{part_id}", part_id


def build_partition_key_from_headers(
    endpoint_id: str, headers: dict
) -> Tuple[str, str]:
    """Construct partition_key from endpoint_id and request headers dict.

    Looks for 'Part-Id' or 'Part-ID' header (case-insensitive matching
    handled by caller).

    Raises:
        ValueError: If Part-Id header is missing.
    """
    part_id = (
        headers.get("part-id")
        or headers.get("Part-Id")
        or headers.get("Part-ID")
    )
    if not part_id:
        raise ValueError(
            "Part-Id header is required to construct partition_key"
        )
    return build_partition_key(endpoint_id, part_id)