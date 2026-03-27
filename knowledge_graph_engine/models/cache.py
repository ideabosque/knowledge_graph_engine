# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import logging
from typing import Any, Dict, Optional

from ..handlers.config import Config


class CascadingCachePurger:
    """
    Handles cascading cache purges for entity dependencies.
    Same pattern as ai_agent_core_engine.
    """

    @staticmethod
    def purge_entity_cascading_cache(
        logger: logging.Logger,
        entity_type: str,
        context_keys: Optional[Dict[str, Any]] = None,
        entity_keys: Optional[Dict[str, Any]] = None,
        cascade_depth: int = 3,
    ) -> None:
        """
        Purge cache for entity and all dependent children.

        Args:
            logger: Logger instance
            entity_type: Entity type (e.g., 'document', 'graph_schema')
            context_keys: Context keys (partition_key, etc.)
            entity_keys: Entity keys (document_uuid, etc.)
            cascade_depth: Maximum cascade depth
        """
        if cascade_depth <= 0:
            return

        entity_config = Config.CACHE_ENTITY_CONFIG.get(entity_type)
        if not entity_config:
            logger.warning(f"No cache config found for entity type: {entity_type}")
            return

        cache_keys = entity_config.get("cache_keys", [])
        for cache_key in cache_keys:
            try:
                from silvaengine_utility.cache import HybridCacheEngine

                cache = HybridCacheEngine(cache_key)
                cache.clear()
                logger.info(f"Purged cache: {cache_key}")
            except Exception as e:
                logger.warning(f"Failed to purge cache {cache_key}: {e}")

        children = Config.CACHE_RELATIONSHIPS.get(entity_type, [])
        for child in children:
            child_entity_type = child.get("entity_type")
            if child_entity_type:
                CascadingCachePurger.purge_entity_cascading_cache(
                    logger=logger,
                    entity_type=child_entity_type,
                    context_keys=context_keys,
                    entity_keys=entity_keys,
                    cascade_depth=cascade_depth - 1,
                )


def purge_entity_cascading_cache(
    logger: logging.Logger,
    entity_type: str,
    context_keys: Optional[Dict[str, Any]] = None,
    entity_keys: Optional[Dict[str, Any]] = None,
    cascade_depth: int = 3,
) -> None:
    """Convenience function for purging cascading cache."""
    CascadingCachePurger.purge_entity_cascading_cache(
        logger=logger,
        entity_type=entity_type,
        context_keys=context_keys,
        entity_keys=entity_keys,
        cascade_depth=cascade_depth,
    )