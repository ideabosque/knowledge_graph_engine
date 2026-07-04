# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import logging
import sys
import threading
import traceback
from typing import Any, Dict, List, Optional

import boto3


class Config:
    """
    Centralized Configuration Class — core business logic settings only.
    Auth-related settings (JWT, Cognito, local users) have been moved to
    silvaengine_gateway.config.GatewayConfig.

    Manages shared configuration variables across the Knowledge Graph Engine.
    Thread-safe singleton pattern aligned with ai_agent_core_engine.
    """

    _initialized: bool = False
    _lock: threading.RLock = threading.RLock()
    _logger: Optional[logging.Logger] = None
    _setting: Dict[str, Any] = {}
    _graph_rag_utils: Dict[str, Any] = {}

    # KnowledgeGraphEngine instance (set by daemon entry point)
    kge: Any = None

    # Backend selection: "dynamodb" (default) or "postgresql"
    DB_BACKEND: str = "dynamodb"

    # PostgreSQL session (only initialized when DB_BACKEND == "postgresql")
    db_session = None

    # PostgreSQL table name prefix (e.g. "kge_") — avoids collisions in
    # shared databases.  Set from ``pg_table_prefix`` setting by
    # ``_initialize_db_session``.  Empty string = no prefix (backward compat).
    PG_TABLE_PREFIX: str = "kge_"

    # Cache Configuration
    CACHE_TTL = 1800
    CACHE_ENABLED: bool = True
    CACHE_NAMES = {
        "models": "knowledge_graph_engine.models.dynamodb",
        "queries": "knowledge_graph_engine.queries",
    }

    # ------------------------------------------------------------------
    # Cache entity metadata (module paths, getters, cache key templates).
    #
    # Backend-aware: DynamoDB repositories use @method_cache stamped with
    # the dynamodb module path. PostgreSQL repositories do not currently
    # use @method_cache, so the PG config is empty.
    # ------------------------------------------------------------------
    CACHE_ENTITY_CONFIG_DYNAMODB = {
        "document": {
            "module": "knowledge_graph_engine.models.dynamodb.document",
            "model_class": "DocumentModel",
            "getter": "get_document",
            "list_resolver": "knowledge_graph_engine.queries.document.resolve_document_list",
            "cache_keys": ["context:partition_key", "key:document_uuid"],
        },
        "graph_schema": {
            "module": "knowledge_graph_engine.models.dynamodb.graph_schema",
            "model_class": "GraphSchemaModel",
            "getter": "get_graph_schema",
            "list_resolver": "knowledge_graph_engine.queries.graph_schema.resolve_graph_schema_list",
            "cache_keys": ["context:partition_key", "key:schema_name"],
        },
        "neo4j_instance": {
            "module": "knowledge_graph_engine.models.dynamodb.neo4j_instance",
            "model_class": "Neo4jInstanceModel",
            "getter": "get_neo4j_instance",
            "list_resolver": "knowledge_graph_engine.models.dynamodb.neo4j_instance.resolve_neo4j_instance_list",
            "cache_keys": ["context:partition_key", "key:instance_id"],
        },
        "request": {
            "module": "knowledge_graph_engine.models.dynamodb.request",
            "model_class": "RequestModel",
            "getter": "get_request",
            "list_resolver": "knowledge_graph_engine.models.dynamodb.request.resolve_request_list",
            "cache_keys": ["context:partition_key", "key:request_uuid"],
        },
        "document_process_error": {
            "module": "knowledge_graph_engine.models.dynamodb.document_process_error",
            "model_class": "DocumentProcessErrorModel",
            "getter": "get_document_process_error",
            "list_resolver": "",
            "cache_keys": ["context:partition_key", "key:process_error_uuid"],
        },
    }

    # PostgreSQL cache config — empty until PG repos opt into caching.
    CACHE_ENTITY_CONFIG_POSTGRESQL: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_cache_entity_config(cls) -> Dict[str, Dict[str, Any]]:
        """Return cache metadata for the active DB_BACKEND."""
        if cls.DB_BACKEND == "postgresql":
            return cls.CACHE_ENTITY_CONFIG_POSTGRESQL
        return cls.CACHE_ENTITY_CONFIG_DYNAMODB

    # ------------------------------------------------------------------
    # Entity cache dependency relationships (cascading invalidation).
    # ------------------------------------------------------------------
    CACHE_RELATIONSHIPS_DYNAMODB = {
        "document": ["request"],
        "graph_schema": ["document"],
        "neo4j_instance": [],
    }

    CACHE_RELATIONSHIPS_POSTGRESQL: Dict[str, List[Dict[str, Any]]] = {}

    @classmethod
    def get_cache_relationships(cls) -> Dict[str, Any]:
        """Return cascade-invalidation relationships for the active backend."""
        if cls.DB_BACKEND == "postgresql":
            return cls.CACHE_RELATIONSHIPS_POSTGRESQL
        return cls.CACHE_RELATIONSHIPS_DYNAMODB

    # AWS services (kept — used by core for Lambda invocation and DynamoDB)
    aws_lambda: Any = None
    aws_s3: Any = None
    aws_sqs: Any = None

    @classmethod
    def initialize(cls, logger: logging.Logger, setting: Dict[str, Any]) -> None:
        if not setting:
            raise RuntimeError("`setting` is required")

        with cls._lock:
            if cls._initialized and cls._setting == setting:
                cls._logger = logger
                return

            try:
                if cls._initialized:
                    cls.reset()

                cls._logger = logger
                cls._setting = dict(setting)

                # Read backend selection (deployment-time, not per request)
                cls.DB_BACKEND = str(setting.get("db_backend", "dynamodb")).lower()
                if cls.DB_BACKEND not in ("dynamodb", "postgresql"):
                    raise ValueError(f"Unknown db_backend: {cls.DB_BACKEND}")

                # KGE keeps AWS services unconditional for both backends
                # (aws_lambda is used for dispatch, S3 for file parsing).
                cls._initialize_aws_services(setting)

                if cls.DB_BACKEND == "dynamodb":
                    cls._initialize_dynamodb_meta(setting)
                elif cls.DB_BACKEND == "postgresql":
                    cls.PG_TABLE_PREFIX = str(
                        setting.get("pg_table_prefix", "kge_")
                    ).strip()
                    cls._initialize_db_session(setting)

                if setting.get("initialize_tables"):
                    cls._initialize_tables(logger)

                cls._initialized = True
                logger.info(
                    f"Configuration initialized successfully (db_backend={cls.DB_BACKEND})."
                )
            except Exception as e:
                sys.stderr.write(f"Config Initialize Error: {e}\n")
                traceback.print_exc(file=sys.stderr)
                logger.exception("Failed to initialize configuration.")
                raise e

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            from .neo4j_connection_manager import Neo4jConnectionManager

            Neo4jConnectionManager.close_all()
            cls._initialized = False
            cls._logger = None
            cls._setting = {}
            cls.kge = None
            cls.aws_lambda = None
            cls.aws_s3 = None
            cls.aws_sqs = None
            cls.db_session = None

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
    def _initialize_dynamodb_meta(cls, setting: Dict[str, Any]) -> None:
        """Initialize PynamoDB BaseModel.Meta credentials from setting."""
        from silvaengine_dynamodb_base import BaseModel

        if (
            setting.get("region_name")
            and setting.get("aws_access_key_id")
            and setting.get("aws_secret_access_key")
        ):
            if hasattr(BaseModel.Meta, "region"):
                BaseModel.Meta.region = setting.get("region_name")
            if hasattr(BaseModel.Meta, "aws_access_key_id"):
                BaseModel.Meta.aws_access_key_id = setting.get("aws_access_key_id")
            if hasattr(BaseModel.Meta, "aws_secret_access_key"):
                BaseModel.Meta.aws_secret_access_key = setting.get(
                    "aws_secret_access_key"
                )

    @classmethod
    def _initialize_db_session(cls, setting: Dict[str, Any]) -> None:
        """Initialize the PostgreSQL database session using SQLAlchemy.

        Expected setting keys: db_host, db_port, db_user, db_password, db_schema,
        and optionally pg_table_prefix (e.g. "kge_") to avoid table name
        collisions in shared databases.
        """
        from urllib.parse import quote_plus

        from sqlalchemy import create_engine
        from sqlalchemy.orm import scoped_session, sessionmaker

        # Set the table prefix on Base BEFORE any model is imported so that
        # declared_attr __tablename__ picks it up at class-definition time.
        from ..models.postgresql.base import Base

        Base.table_prefix = str(setting.get("pg_table_prefix", "") or "")
        cls._logger.info(f"PostgreSQL table prefix set to '{Base.table_prefix}'.")

        password = quote_plus(setting["db_password"])
        connection_string = (
            f"postgresql+psycopg2://{setting['db_user']}:{password}"
            f"@{setting['db_host']}:{setting['db_port']}/{setting['db_schema']}"
        )

        engine = create_engine(
            connection_string,
            pool_recycle=7200,
            pool_size=10,
            pool_pre_ping=True,
            echo=False,
        )

        cls.db_session = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=engine)
        )

    @classmethod
    def _initialize_tables(cls, logger: logging.Logger) -> None:
        if cls.DB_BACKEND == "dynamodb":
            from ..models.dynamodb.utils import initialize_tables

            initialize_tables(logger)
        elif cls.DB_BACKEND == "postgresql":
            from ..models.postgresql.utils import initialize_tables as pg_init

            pg_init(logger, cls.db_session)

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
        from ..models.repositories import get_repo

        with cls._lock:
            cached = cls._graph_rag_utils.get(partition_key)
            if cached is not None:
                return cached

            driver = Neo4jConnectionManager.get_driver(partition_key)

            # Use the repository boundary to get the active Neo4j instance.
            # resolve_active returns a normalized dict; extract neo4j_database.
            repo = get_repo("neo4j_instance")
            instance = repo.resolve_active(partition_key)
            if instance is None:
                raise RuntimeError(
                    f"No active Neo4j instance for partition: {partition_key}"
                )
            database = instance.get("neo4j_database") or "neo4j"

            graph_rag = GraphRAGUtil(
                driver=driver,
                neo4j_database=database,
                settings=cls._setting,
            )
            cls._graph_rag_utils[partition_key] = graph_rag
            return graph_rag

    @classmethod
    def clear_graph_rag_util(cls, partition_key: str) -> None:
        with cls._lock:
            cls._graph_rag_utils.pop(partition_key, None)
