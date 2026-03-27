# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import logging
import sys
import threading
import traceback
from typing import Any, Dict, Optional

import boto3


class Config:
    """
    Centralized Configuration Class
    Manages shared configuration variables across the Knowledge Graph Engine.
    Thread-safe singleton pattern aligned with ai_agent_core_engine.
    """

    _initialized: bool = False
    _lock: threading.RLock = threading.RLock()
    _logger: Optional[logging.Logger] = None
    _setting: Dict[str, Any] = {}
    # Cache Configuration
    CACHE_TTL = 1800
    CACHE_ENABLED: bool = True
    CACHE_NAMES = {
        "models": "knowledge_graph_engine.models",
        "queries": "knowledge_graph_engine.queries",
    }

    CACHE_ENTITY_CONFIG = {
        "document": {
            "module": "knowledge_graph_engine.models.document",
            "model_class": "DocumentModel",
            "getter": "get_document",
            "list_resolver": "knowledge_graph_engine.queries.document.resolve_document_list",
            "cache_keys": ["context:partition_key", "key:document_uuid"],
        },
        "graph_schema": {
            "module": "knowledge_graph_engine.models.graph_schema",
            "model_class": "GraphSchemaModel",
            "getter": "get_graph_schema",
            "list_resolver": "knowledge_graph_engine.queries.graph_schema.resolve_graph_schema_list",
            "cache_keys": ["context:partition_key", "key:schema_name"],
        },
        "neo4j_instance": {
            "module": "knowledge_graph_engine.models.neo4j_instance",
            "model_class": "Neo4jInstanceModel",
            "getter": "get_neo4j_instance",
            "list_resolver": "knowledge_graph_engine.queries.neo4j_instance.resolve_neo4j_instance_list",
            "cache_keys": ["context:partition_key", "key:instance_id"],
        },
        "request": {
            "module": "knowledge_graph_engine.models.request",
            "model_class": "RequestModel",
            "getter": "get_request",
            "list_resolver": "knowledge_graph_engine.queries.request.resolve_request_list",
            "cache_keys": ["context:partition_key", "key:request_uuid"],
        },
    }

    CACHE_RELATIONSHIPS = {
        "document": ["request"],
        "graph_schema": ["document"],
        "neo4j_instance": [],
    }

    @classmethod
    def get_cache_entity_config(cls) -> Dict[str, Dict[str, Any]]:
        return cls.CACHE_ENTITY_CONFIG

    @classmethod
    def initialize(cls, logger: logging.Logger, setting: Dict[str, Any]) -> None:
        if not setting:
            raise RuntimeError("`setting` is required")
        elif cls._initialized:
            return

        with cls._lock:
            if not cls._initialized:
                try:
                    cls._logger = logger
                    cls._setting = setting
                    cls._initialize_aws_services(setting)

                    if setting.get("initialize_tables"):
                        cls._initialize_tables(logger)

                    cls._initialized = True
                except Exception as e:
                    sys.stderr.write(f"Config Initialize Error: {e}\n")
                    traceback.print_exc(file=sys.stderr)
                    logger.exception("Failed to initialize configuration.")
                    raise e

    @classmethod
    def _initialize_aws_services(cls, setting: Dict[str, Any]) -> None:
        if all(
            setting.get(k)
            for k in ["region_name", "aws_access_key_id", "aws_secret_access_key"]
        ):
            aws_credentials = {
                "region_name": setting["region_name"],
                "aws_access_key_id": setting["aws_access_key_id"],
                "aws_secret_access_key": setting["aws_secret_access_key"],
            }
        else:
            aws_credentials = {}

        cls.aws_lambda = boto3.client("lambda", **aws_credentials)

    @classmethod
    def _initialize_tables(cls, logger: logging.Logger) -> None:
        from ..models.utils import initialize_tables

        initialize_tables(logger)

    @classmethod
    def get_cache_name(cls, module_type: str, model_name: str) -> str:
        base_name = cls.CACHE_NAMES.get(
            module_type, f"knowledge_graph_engine.{module_type}"
        )
        return f"{base_name}.{model_name}"

    @classmethod
    def get_cache_ttl(cls) -> int:
        return cls.CACHE_TTL

    @classmethod
    def is_cache_enabled(cls) -> bool:
        return cls.CACHE_ENABLED

    @classmethod
    def get_cache_relationships(cls) -> Dict[str, list]:
        return cls.CACHE_RELATIONSHIPS

    @classmethod
    def get_setting(cls) -> Dict[str, Any]:
        if not cls._initialized:
            raise RuntimeError("Configuration not initialized")

        return cls._setting

    @classmethod
    def get_logger(cls) -> logging.Logger:
        if cls._logger:
            return cls._logger

        return logging.getLogger()

    @classmethod
    def get_graph_rag_util(cls, partition_key: str) -> Any:
        from .neo4j_connection_manager import Neo4jConnectionManager
        from ..utils.graph_rag_util import GraphRAGUtil
        from ..models.neo4j_instance import Neo4jInstanceModel

        driver = Neo4jConnectionManager.get_driver(partition_key)
        try:
            instance = Neo4jInstanceModel.get(partition_key, "default")
            database = instance.neo4j_database or "neo4j"
        except Exception:
            database = "neo4j"

        return GraphRAGUtil(
            driver=driver,
            neo4j_database=database,
            settings=cls._setting,
        )