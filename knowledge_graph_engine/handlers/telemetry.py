# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

"""Handler telemetry: emit structured events and measure handler duration."""

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


def emit_handler_event(
    info: Any,
    *,
    operation: str,
    handler: str,
    duration_ms: Optional[float] = None,
    tenant: Optional[str] = None,
    namespace: Optional[str] = None,
    error_code: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a structured log event for a handler operation.

    Args:
        info: Graphene ResolveInfo or shim object with .context dict.
        operation: The operation name (e.g., "extract", "search").
        handler: The handler domain name (e.g., "extraction", "search").
        duration_ms: Wall-clock duration in milliseconds.
        tenant: Partition key / tenant identifier.
        namespace: Additional namespace context.
        error_code: Error code if the handler raised a domain error.
        extra: Additional key-value pairs to include in the event.
    """
    context = info.context if hasattr(info, "context") else {}
    log = context.get("logger") or logger

    event: Dict[str, Any] = {
        "handler": handler,
        "operation": operation,
    }

    if duration_ms is not None:
        event["duration_ms"] = round(duration_ms, 2)

    if tenant:
        event["tenant"] = tenant
    elif context.get("partition_key"):
        event["tenant"] = context["partition_key"]

    if namespace:
        event["namespace"] = namespace

    if error_code:
        event["error_code"] = error_code

    if extra:
        event.update(extra)

    log.info("handler_event: %s", event)


@contextmanager
def measure_handler_duration(
    info: Any,
    *,
    operation: str,
    handler: str,
    tenant: Optional[str] = None,
    namespace: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    """Context manager that measures wall-clock duration of a handler call.

    On success, emits a handler_event with duration_ms.
    On failure, emits a handler_event with duration_ms and error_code
    extracted from ``exc.code`` (falls back to "system_error").

    Usage::

        with measure_handler_duration(info, operation="extract", handler="extraction"):
            result = _extract(info, **kwargs)
    """
    start = time.monotonic()
    error_code = None
    try:
        yield
    except Exception as exc:
        error_code = getattr(exc, "code", "system_error")
        raise
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        emit_handler_event(
            info,
            operation=operation,
            handler=handler,
            duration_ms=duration_ms,
            tenant=tenant,
            namespace=namespace,
            error_code=error_code,
            extra=extra,
        )