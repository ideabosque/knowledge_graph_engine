# -*- coding: utf-8 -*-
"""PostgreSQL batch loader base helpers."""
from __future__ import print_function

__author__ = "silvaengine"

from promise.dataloader import DataLoader

from ....handlers.config import Config
from ..base import normalize_row


class SafeDataLoader(DataLoader):
    """Base DataLoader with the same error-isolation behavior as DynamoDB loaders."""

    def __init__(self, logger=None, cache_enabled=True, **kwargs):
        super(SafeDataLoader, self).__init__(**kwargs)
        self.logger = logger
        self.cache_enabled = cache_enabled and Config.is_cache_enabled()

    def dispatch(self):
        try:
            return super(SafeDataLoader, self).dispatch()
        except Exception as exc:  # pragma: no cover - defensive
            if self.logger:
                self.logger.exception(exc)
            raise


__all__ = ["SafeDataLoader", "normalize_row"]