# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from promise.dataloader import DataLoader


class SafeDataLoader(DataLoader):
    """Base DataLoader that logs and swallows exceptions."""

    def batch_load_fn(self, keys):
        raise NotImplementedError