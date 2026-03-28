# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import logging
import sys
import threading
import traceback
from typing import Any, Dict, Optional

import boto3


class LocalUser:
    """Simple local user for JWT auth."""

    def __init__(self, username: str, hashed_password: str, roles: list = None):
        self.username = username
        self.hashed_password = hashed_password
        self.roles = roles or []

    def verify(self, password: str) -> bool:
        try:
            from passlib.context import CryptContext

            ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
            return ctx.verify(password, self.hashed_password)
        except ImportError:
            return password == self.hashed_password


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
    _USERS: Dict[str, LocalUser] = {}
    _graph_rag_utils: Dict[str, Any] = {}

    # KnowledgeGraphEngine instance (set by fastapi entry point)
    kge: Any = None

    # Auth settings
    auth_provider: str = "local"  # "local" or "cognito"
    jwt_secret_key: str = "CHANGEME"
    jwt_algorithm: str = "HS256"
    access_token_exp: int = 15  # minutes
    admin_username: str = ""
    admin_password: str = ""
    admin_static_token: str = ""

    # Cognito settings
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    cognito_app_secret: str = ""
    jwks_endpoint: str = ""
    jwks_cache_ttl: int = 3600
    issuer: str = ""
    aws_cognito_idp: Any = None

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
            "list_resolver": "knowledge_graph_engine.models.neo4j_instance.resolve_neo4j_instance_list",
            "cache_keys": ["context:partition_key", "key:instance_id"],
        },
        "request": {
            "module": "knowledge_graph_engine.models.request",
            "model_class": "RequestModel",
            "getter": "get_request",
            "list_resolver": "knowledge_graph_engine.models.request.resolve_request_list",
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

        with cls._lock:
            if cls._initialized and cls._setting == setting:
                cls._logger = logger
                return

            try:
                if cls._initialized:
                    cls.reset()

                cls._logger = logger
                cls._setting = dict(setting)
                cls._initialize_aws_services(setting)
                cls._initialize_auth(setting)

                if setting.get("initialize_tables"):
                    cls._initialize_tables(logger)

                cls._initialized = True
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
            cls._USERS = {}
            cls.kge = None
            cls.auth_provider = "local"
            cls.jwt_secret_key = "CHANGEME"
            cls.jwt_algorithm = "HS256"
            cls.access_token_exp = 15
            cls.admin_username = ""
            cls.admin_password = ""
            cls.admin_static_token = ""
            cls.cognito_user_pool_id = ""
            cls.cognito_app_client_id = ""
            cls.cognito_app_secret = ""
            cls.jwks_endpoint = ""
            cls.jwks_cache_ttl = 3600
            cls.issuer = ""
            cls.aws_cognito_idp = None
            if hasattr(cls, "aws_lambda"):
                cls.aws_lambda = None

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
    def _initialize_auth(cls, setting: Dict[str, Any]) -> None:
        cls.auth_provider = setting.get("auth_provider", "local")
        cls.jwt_secret_key = setting.get("jwt_secret_key", "CHANGEME")
        cls.jwt_algorithm = setting.get("jwt_algorithm", "HS256")
        cls.access_token_exp = int(setting.get("access_token_exp", 15))
        cls.admin_username = setting.get("admin_username", "")
        cls.admin_password = setting.get("admin_password", "")
        cls.admin_static_token = setting.get("admin_static_token", "")

        if cls.auth_provider == "cognito":
            cls.cognito_user_pool_id = setting.get("cognito_user_pool_id", "")
            cls.cognito_app_client_id = setting.get("cognito_app_client_id", "")
            cls.cognito_app_secret = setting.get("cognito_app_secret", "")
            region = setting.get("region_name", "us-east-1")
            cls.issuer = (
                f"https://cognito-idp.{region}.amazonaws.com/{cls.cognito_user_pool_id}"
            )
            cls.jwks_endpoint = setting.get(
                "cognito_jwks_url",
                f"{cls.issuer}/.well-known/jwks.json",
            )
            cls.jwks_cache_ttl = int(setting.get("jwks_cache_ttl", 3600))

            if all(
                setting.get(k)
                for k in ["region_name", "aws_access_key_id", "aws_secret_access_key"]
            ):
                cls.aws_cognito_idp = boto3.client(
                    "cognito-idp",
                    region_name=setting["region_name"],
                    aws_access_key_id=setting["aws_access_key_id"],
                    aws_secret_access_key=setting["aws_secret_access_key"],
                )

        # Load local users file if configured
        user_file = setting.get("local_user_file")
        if user_file:
            cls._load_users(user_file)

    @classmethod
    def _load_users(cls, filepath: str) -> None:
        import json
        import os

        if not os.path.exists(filepath):
            return
        try:
            with open(filepath) as f:
                users_data = json.load(f)
            for u in users_data:
                cls._USERS[u["username"]] = LocalUser(
                    username=u["username"],
                    hashed_password=u.get("hashed_password", ""),
                    roles=u.get("roles", []),
                )
        except Exception as e:
            if cls._logger:
                cls._logger.warning(f"Failed to load users from {filepath}: {e}")

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
        from ..models.neo4j_instance import get_active_neo4j_instance

        with cls._lock:
            cached = cls._graph_rag_utils.get(partition_key)
            if cached is not None:
                return cached

            driver = Neo4jConnectionManager.get_driver(partition_key)
            try:
                instance = get_active_neo4j_instance(partition_key)
                database = instance.neo4j_database or "neo4j"
            except Exception:
                database = "neo4j"

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
