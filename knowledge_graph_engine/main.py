#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import logging
import os
import sys
from typing import Any, Dict, List

from graphene import Schema
from silvaengine_utility import Graphql

from .handlers.config import Config
from .handlers.partition_manager import PartitionManager
from .handlers.schema import Mutations, Query, type_class


def deploy() -> List:
    return [
        {
            "service": "Knowledge Graph Engine",
            "class": "KnowledgeGraphEngine",
            "functions": {
                "knowledge_graph_graphql": {
                    "is_static": False,
                    "label": "Knowledge Graph Engine",
                    "query": [
                        {"action": "ping", "label": "Ping"},
                        {"action": "document", "label": "View Document"},
                        {"action": "documentList", "label": "List Documents"},
                        {"action": "graphSchema", "label": "View Graph Schema"},
                        {"action": "graphSchemaList", "label": "List Graph Schemas"},
                        {"action": "neo4jInstance", "label": "View Neo4j Instance"},
                        {
                            "action": "neo4jInstanceList",
                            "label": "List Neo4j Instances",
                        },
                        {"action": "request", "label": "View Request"},
                        {"action": "requestList", "label": "List Requests"},
                        {"action": "search", "label": "Knowledge Graph Search"},
                        {"action": "rag", "label": "RAG Query"},
                    ],
                    "mutation": [
                        {
                            "action": "insertUpdateDocument",
                            "label": "Create Update Document",
                        },
                        {"action": "deleteDocument", "label": "Delete Document"},
                        {
                            "action": "insertUpdateGraphSchema",
                            "label": "Create Update Graph Schema",
                        },
                        {"action": "deleteGraphSchema", "label": "Delete Graph Schema"},
                        {
                            "action": "insertUpdateNeo4jInstance",
                            "label": "Register Neo4j Instance",
                        },
                        {
                            "action": "deleteNeo4jInstance",
                            "label": "Deregister Neo4j Instance",
                        },
                        {
                            "action": "executeExtract",
                            "label": "Extract Knowledge Graph",
                        },
                    ],
                    "type": "RequestResponse",
                    "support_methods": ["POST"],
                    "is_auth_required": False,
                    "is_graphql": True,
                    "settings": "knowledge_graph_engine",
                    "disabled_in_resources": True,
                },
                "async_extract_knowledge_graph": {
                    "is_static": False,
                    "label": "Async Extract Knowledge Graph",
                    "type": "Event",
                    "support_methods": ["POST"],
                    "is_auth_required": False,
                    "is_graphql": False,
                    "settings": "knowledge_graph_engine",
                    "disabled_in_resources": True,
                },
            },
        }
    ]


class KnowledgeGraphEngine(Graphql):
    def __init__(self, logger: logging.Logger, **setting: Any) -> None:
        from silvaengine_dynamodb_base import BaseModel

        Graphql.__init__(self, logger, **setting)

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

        Config.initialize(logger, setting)

    def knowledge_graph_graphql(self, **params: Any) -> Any:
        self._apply_partition_defaults(params)
        return self.execute(self.__class__.build_graphql_schema(), **params)

    def async_extract_knowledge_graph(self, **params: Any) -> Any:
        self._apply_partition_defaults(params)

        from .handlers.extractor import Extractor
        from .utils.listener import create_listener_info

        info = create_listener_info(self.logger, "extract", self.setting, **params)
        extractor = Extractor(info)
        return extractor.extract(**params)

    @staticmethod
    def build_graphql_schema() -> Schema:
        return Schema(
            query=Query,
            mutation=Mutations,
            types=type_class(),
        )

    def _apply_partition_defaults(self, params: Dict[str, Any]) -> None:
        endpoint_id = params.get("endpoint_id", self.setting.get("endpoint_id"))
        part_id = params.get("metadata", {}).get(
            "part_id",
            params.get("part_id", self.setting.get("part_id")),
        )

        if params.get("context") is None:
            params["context"] = {}

        if "endpoint_id" not in params["context"]:
            params["context"]["endpoint_id"] = endpoint_id
        if "part_id" not in params["context"]:
            params["context"]["part_id"] = part_id

        if "partition_key" not in params["context"]:
            if not endpoint_id or not part_id:
                self.logger.error(
                    f"Missing endpoint_id or part_id: endpoint_id={endpoint_id}, part_id={part_id}"
                )
                raise ValueError(
                    "Both 'endpoint_id' and 'part_id' are required to generate 'partition_key'."
                )
            else:
                params["context"]["partition_key"] = (
                    PartitionManager.build_partition_key(endpoint_id, part_id)
                )

    def daemon(self):
        try:
            import uvicorn

            from .handlers.auth_router import router as auth_router
            from .handlers.fastapi_app import app
            from .handlers.middleware import FlexJWTMiddleware

            Config.kge = self

            # JWT guard
            app.add_middleware(FlexJWTMiddleware, public_paths=["/health"])
            # mount /auth routes
            app.include_router(auth_router)

            port = int(self.setting.get("port", 8000))
            self.logger.info(
                f"Starting server on port {port} (auth={self.setting.get('auth_provider', 'local')})"
            )

            uvicorn.run(app, host="0.0.0.0", port=port)
        except KeyboardInterrupt:
            self.logger.info("Server interrupted by user.")
        except Exception as e:
            self.logger.exception("Fatal server error")
            sys.exit(1)


def main():
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("knowledge_graph_engine")

    engine = KnowledgeGraphEngine(
        logger,
        **{
            # AWS
            "region_name": os.getenv("region_name"),
            "aws_access_key_id": os.getenv("aws_access_key_id"),
            "aws_secret_access_key": os.getenv("aws_secret_access_key"),
            # Tenant
            "endpoint_id": os.getenv("endpoint_id"),
            "part_id": os.getenv("part_id"),
            # Tables
            "initialize_tables": int(os.getenv("initialize_tables", "0")),
            "cache_enabled": int(os.getenv("cache_enabled", "0")),
            # LLM
            "llm_type": os.getenv("llm_type", "openai"),
            "llm_name": os.getenv("llm_name", "gpt-4o"),
            "openai_api_key": os.getenv("openai_api_key"),
            "openai_base_url": os.getenv("openai_base_url"),
            "anthropic_api_key": os.getenv("anthropic_api_key"),
            "anthropic_base_url": os.getenv("anthropic_base_url"),
            "ollama_host": os.getenv("ollama_host", "http://localhost:11434"),
            "mistralai_api_key": os.getenv("mistralai_api_key"),
            "vertexai_system_instruction": os.getenv("vertexai_system_instruction"),
            # Embeddings
            "embedding_provider": os.getenv("embedding_provider"),
            "embedding_model": os.getenv("embedding_model", "text-embedding-3-small"),
            # Neo4j
            "neo4j_uri": os.getenv("neo4j_uri", "bolt://localhost:7687"),
            "neo4j_username": os.getenv("neo4j_username", "neo4j"),
            "neo4j_password": os.getenv("neo4j_password"),
            "neo4j_database": os.getenv("neo4j_database", "neo4j"),
            # Auth
            "auth_provider": os.getenv("AUTH_PROVIDER", "local"),
            "jwt_secret_key": os.getenv("JWT_SECRET_KEY", "CHANGEME"),
            "jwt_algorithm": os.getenv("JWT_ALGORITHM", "HS256"),
            "access_token_exp": os.getenv("ACCESS_TOKEN_EXP", "15"),
            "admin_username": os.getenv("ADMIN_USERNAME", ""),
            "admin_password": os.getenv("ADMIN_PASSWORD", ""),
            "admin_static_token": os.getenv("ADMIN_STATIC_TOKEN", ""),
            "local_user_file": os.getenv("LOCAL_USER_FILE"),
            # Cognito
            "cognito_user_pool_id": os.getenv("COGNITO_USER_POOL_ID", ""),
            "cognito_app_client_id": os.getenv("COGNITO_APP_CLIENT_ID", ""),
            "cognito_app_secret": os.getenv("COGNITO_APP_SECRET", ""),
            "cognito_jwks_url": os.getenv("COGNITO_JWKS_URL"),
            # Server
            "port": int(os.getenv("PORT", "8000")),
        },
    )
    engine.daemon()
