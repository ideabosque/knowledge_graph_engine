# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from decimal import Decimal
from typing import Any, Dict


def normalize_to_json(obj: Any) -> Dict[str, Any]:
    """
    Convert a DynamoDB model to JSON-serializable dict.
    Same pattern as ai_agent_core_engine.
    """
    if obj is None:
        return {}

    if isinstance(obj, dict):
        data = obj
    elif hasattr(obj, "attribute_values"):
        data = getattr(obj, "attribute_values", {})
    elif hasattr(obj, "__dict__"):
        data = obj.__dict__
    else:
        return {"value": obj}

    result = {}
    for key, value in data.items():
        if isinstance(value, Decimal):
            result[key] = int(value) if value % 1 == 0 else float(value)
        elif isinstance(value, (list, tuple)):
            result[key] = [normalize_to_json(v) for v in value]
        elif isinstance(value, dict):
            result[key] = {k: normalize_to_json(v) for k, v in value.items()}
        else:
            result[key] = value

    return result
