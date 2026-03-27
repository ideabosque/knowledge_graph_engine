# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from types import SimpleNamespace
import logging
from typing import Any, Dict


def create_listener_info(
    logger: logging.Logger,
    field_name: str,
    setting: Dict[str, Any],
    **kwargs: Any,
) -> Any:
    """
    Build a minimal ResolveInfo for async listener contexts.
    Same pattern as ai_agent_core_engine.
    """
    context = {
        "setting": setting,
        "endpoint_id": kwargs.get("endpoint_id"),
        "logger": logger,
        "part_id": kwargs.get("part_id"),
        "connection_id": kwargs.get("connection_id"),
        "context": kwargs.get("context", {}),
        "partition_key": kwargs.get(
            "partition_key", kwargs.get("context", {}).get("partition_key")
        ),
    }

    if "metadata" in kwargs and isinstance(kwargs["metadata"], dict):
        context.update(kwargs.get("metadata", {}))

    return SimpleNamespace(field_name=field_name, context=context, logger=logger)
