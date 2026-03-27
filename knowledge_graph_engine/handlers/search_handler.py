# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, Optional

from .config import Config


class SearchHandler:
    """
    Delegates to GraphRAGUtil's 4 search modes.
    All use neo4j_database parameter per neo4j-graphrag-python convention.
    """

    def __init__(self, info: Any) -> None:
        self.info = info
        self.context = info.context if hasattr(info, "context") else {}

    def search(
        self,
        partition_key: str,
        query_text: str,
        search_mode: str = "text2cypher",
        schema_name: Optional[str] = None,
        index_name: str = "vector",
        retrieval_query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
        page: int = 1,
        limit: int = 10,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute search using one of the 4 modes:
        - vector: Semantic similarity search
        - text2cypher: LLM generates Cypher query
        - vector_cypher: Vector + custom Cypher traversal
        - hybrid: Vector + fulltext combined
        """
        graph_rag = Config.get_graph_rag_util(partition_key)

        if search_mode == "vector":
            results = graph_rag.vector_search(
                query_text=query_text,
                index_name=index_name,
                filters=filters,
                top_k=top_k,
            )

        elif search_mode == "text2cypher":
            neo4j_schema = self._load_neo4j_schema(partition_key, schema_name or "default")
            results = graph_rag.text2cypher_search(
                query_text=query_text,
                neo4j_schema=neo4j_schema,
                top_k=top_k,
            )

        elif search_mode == "vector_cypher":
            results = graph_rag.vector_cypher_search(
                query_text=query_text,
                index_name=index_name,
                retrieval_query=retrieval_query or "RETURN node, score",
                top_k=top_k,
            )

        elif search_mode == "hybrid":
            results = graph_rag.hybrid_search(
                query_text=query_text,
                vector_index_name=index_name,
                fulltext_index_name=kwargs.get("fulltext_index_name", "fulltext"),
                top_k=top_k,
            )

        else:
            raise ValueError(f"Unsupported search_mode: {search_mode}")

        formatted = self._format_results(results, page, limit)

        # Record the search request
        self._record_request(partition_key, query_text, search_mode, formatted)

        return formatted

    def _record_request(
        self,
        partition_key: str,
        query_text: str,
        search_mode: str,
        formatted_results: Dict[str, Any],
    ) -> None:
        """Persist search request to kge-requests table."""
        try:
            from ..models.request import insert_update_request
            from ..utils.listener import create_listener_info

            logger = self.context.get("logger")
            setting = self.context.get("setting", {})
            info = create_listener_info(
                logger, "search", setting, partition_key=partition_key
            ) if logger else self.info

            insert_update_request(
                info,
                partition_key=partition_key,
                user_query=query_text,
                search_mode=search_mode,
                results=formatted_results.get("results", []),
                updated_by="search_handler",
            )
        except Exception as e:
            logger = self.context.get("logger")
            if logger:
                logger.warning(f"Failed to record search request: {e}")

    def _load_neo4j_schema(self, partition_key: str, schema_name: str) -> Optional[str]:
        """Load the partition's schema string for text2cypher generation."""
        from ..models.graph_schema import get_graph_schema

        try:
            record = get_graph_schema(partition_key, schema_name)
            return record.neo4j_schema_string if record else None
        except Exception:
            return None

    def _format_results(
        self, results: Any, page: int = 1, limit: int = 10
    ) -> Dict[str, Any]:
        """Format search results with pagination."""
        if hasattr(results, "items") and results.items is not None:
            items = results.items
        elif hasattr(results, "retriever_result"):
            items = results.retriever_result
        elif hasattr(results, "results"):
            items = results.results
        elif isinstance(results, list):
            items = results
        else:
            items = []

        # Convert RetrieverResultItem objects to dicts for JSON serialization
        serialized = []
        for item in items:
            if hasattr(item, "model_dump"):
                serialized.append(item.model_dump())
            elif hasattr(item, "__dict__"):
                serialized.append(item.__dict__)
            else:
                serialized.append(item)

        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_items = serialized[start_idx:end_idx]

        return {
            "results": paginated_items,
            "total": len(serialized),
            "page": page,
            "limit": limit,
        }
