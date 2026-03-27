# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from neo4j_graphrag.generation import GraphRAG
from neo4j_graphrag.generation.prompts import RagTemplate
from neo4j_graphrag.retrievers import VectorRetriever, HybridRetriever

from .config import Config


class RAGHandler:
    """
    RAG handler using GraphRAG with configurable retriever mode.
    Uses neo4j_database (not database) per neo4j-graphrag-python convention.
    """

    def __init__(self, info: Any) -> None:
        self.info = info
        self.context = info.context if hasattr(info, "context") else {}

    def rag(
        self,
        partition_key: str,
        query_text: str,
        search_mode: str = "vector",
        schema_name: Optional[str] = None,
        index_name: str = "vector",
        top_k: int = 5,
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute RAG query using GraphRAG with configurable retriever.

        Args:
            partition_key: Tenant partition key
            query_text: User query
            search_mode: Retriever mode (vector, hybrid)
            schema_name: Schema name for context enrichment
            index_name: Vector index name
            top_k: Number of results to retrieve
            prompt: Optional custom prompt template

        Returns:
            Dict with answer and context
        """
        graph_rag = Config.get_graph_rag_util(partition_key)

        retriever = self._build_retriever(graph_rag, search_mode, index_name)

        schema_context = ""
        if schema_name:
            schema_context = self._load_schema_context(partition_key, schema_name)

        rag_kwargs = {"llm": graph_rag.llm, "retriever": retriever}
        if prompt:
            rag_kwargs["prompt_template"] = RagTemplate(template=prompt)

        rag = GraphRAG(**rag_kwargs)
        full_query = f"{schema_context}{query_text}" if schema_context else query_text

        result = rag.search(
            query_text=full_query,
            retriever_config={"top_k": top_k},
            return_context=True,
        )

        # Serialize context items for JSON output
        context_items = []
        if result.retriever_result and hasattr(result.retriever_result, "items"):
            for item in result.retriever_result.items:
                if hasattr(item, "model_dump"):
                    context_items.append(item.model_dump())
                else:
                    context_items.append(item)

        rag_result = {
            "answer": result.answer,
            "context": context_items,
        }

        # Record the RAG request with results
        self._record_request(partition_key, query_text, search_mode, rag_result)

        return rag_result

    def _record_request(
        self,
        partition_key: str,
        query_text: str,
        search_mode: str,
        rag_result: Dict[str, Any],
    ) -> None:
        """Persist RAG request to kge-requests table."""
        try:
            from ..models.request import insert_update_request
            from ..utils.listener import create_listener_info

            logger = self.context.get("logger")
            setting = self.context.get("setting", {})
            info = create_listener_info(
                logger, "rag", setting, partition_key=partition_key
            ) if logger else self.info

            insert_update_request(
                info,
                partition_key=partition_key,
                user_query=query_text,
                search_mode=f"rag:{search_mode}",
                results=[rag_result],
                updated_by="rag_handler",
            )
        except Exception as e:
            logger = self.context.get("logger")
            if logger:
                logger.warning(f"Failed to record RAG request: {e}")

    def _build_retriever(self, graph_rag: Any, search_mode: str, index_name: str) -> Any:
        """Create retriever matching the search mode. All use neo4j_database."""
        if search_mode == "vector":
            return VectorRetriever(
                driver=graph_rag.driver,
                index_name=index_name,
                embedder=graph_rag.embedder,
                neo4j_database=graph_rag.neo4j_database,
            )
        elif search_mode == "hybrid":
            return HybridRetriever(
                driver=graph_rag.driver,
                vector_index_name=index_name,
                fulltext_index_name="fulltext",
                embedder=graph_rag.embedder,
                neo4j_database=graph_rag.neo4j_database,
            )
        else:
            return VectorRetriever(
                driver=graph_rag.driver,
                index_name=index_name,
                embedder=graph_rag.embedder,
                neo4j_database=graph_rag.neo4j_database,
            )

    def _load_schema_context(self, partition_key: str, schema_name: str) -> str:
        """Load schema context for RAG enrichment."""
        from ..models.graph_schema import get_graph_schema

        try:
            record = get_graph_schema(partition_key, schema_name or "default")
            if record and record.neo4j_schema_string:
                return f"\nGraph schema for this tenant:\n{record.neo4j_schema_string}\n"
        except Exception:
            pass
        return ""
