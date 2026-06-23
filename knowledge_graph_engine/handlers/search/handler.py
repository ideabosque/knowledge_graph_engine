# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

from typing import Any, Dict, List, Optional, TypedDict

from graphene import ResolveInfo

from ..telemetry import measure_handler_duration


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------


class SearchHandlerError(Exception):
    """Base error for search handler."""

    code = "system_error"


class RAGHandlerError(Exception):
    """Base error for RAG handler."""

    code = "system_error"


# ---------------------------------------------------------------------------
# TypedDicts
# ---------------------------------------------------------------------------


class SearchResult(TypedDict, total=False):
    results: List[Dict[str, Any]]
    total: int
    page: int
    limit: int


class RAGResult(TypedDict, total=False):
    answer: str
    context: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Private implementations
# ---------------------------------------------------------------------------


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
        index_name: str = "vector",
        retrieval_query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
        page: int = 1,
        limit: int = 10,
        is_result_formatter: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute search using one of the 4 modes:
        - vector: Semantic similarity search
        - text2cypher: LLM generates Cypher query
        - vector_cypher: Vector + custom Cypher traversal
        - hybrid: Vector + fulltext combined
        """
        from ..config import Config

        graph_rag = Config.get_graph_rag_util(partition_key)
        if search_mode == "vector":
            results = graph_rag.vector_search(
                query_text=query_text,
                index_name=index_name,
                filters=filters,
                top_k=top_k,
                is_result_formatter=is_result_formatter,
            )

        elif search_mode == "text2cypher":
            neo4j_schema = self._load_neo4j_schema(partition_key)
            examples = self._load_text2cypher_examples(partition_key)
            results = graph_rag.text2cypher_search(
                query_text=query_text,
                neo4j_schema=neo4j_schema,
                top_k=top_k,
                is_result_formatter=is_result_formatter,
                examples=examples,
            )

        elif search_mode == "vector_cypher":
            # retrieval_query = retrieval_query or "RETURN node, score"
            retrieval_query = retrieval_query or "MATCH (node)<-[:FROM_CHUNK]-(rel_node) RETURN rel_node, score"
            results = graph_rag.vector_cypher_search(
                query_text=query_text,
                index_name=index_name,
                retrieval_query=retrieval_query,
                top_k=top_k,
                is_result_formatter=is_result_formatter,
            )

        elif search_mode == "hybrid":
            results = graph_rag.hybrid_search(
                query_text=query_text,
                vector_index_name=index_name,
                fulltext_index_name=kwargs.get("fulltext_index_name", "fulltext"),
                top_k=top_k,
                is_result_formatter=is_result_formatter,
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
            from ...models.repositories import get_repo
            from ...utils.listener import create_listener_info

            logger = self.context.get("logger")
            setting = self.context.get("setting", {})
            info = create_listener_info(
                logger, "search", setting, partition_key=partition_key
            ) if logger else self.info

            repo = get_repo("request")
            repo.insert_update(
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

    def _load_neo4j_schema(self, partition_key: str) -> Optional[str]:
        """Load the active schema string for text2cypher generation."""
        from ...models.repositories import get_repo

        try:
            repo = get_repo("graph_schema")
            record = repo.resolve_active(partition_key)
            return record.get("neo4j_schema_string") if record else None
        except Exception:
            return None

    def _load_text2cypher_examples(self, partition_key: str) -> Optional[list]:
        """Load text2cypher examples from the active graph schema record.

        The examples field is a JSON-encoded list of strings, where each
        string is a query→Cypher example pair, e.g.:
        "Find flights from CDG to JFK Business: MATCH (f:Flight) WHERE f.route CONTAINS 'CDG' AND f.route CONTAINS 'JFK' AND f.cabinClass = 'Business' RETURN f"
        """
        import json

        from ...models.repositories import get_repo

        try:
            repo = get_repo("graph_schema")
            record = repo.resolve_active(partition_key)
            if record and record.get("text2cypher_examples"):
                return json.loads(record["text2cypher_examples"])
        except (json.JSONDecodeError, Exception):
            pass
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
        index_name: str = "vector",
        top_k: int = 5,
        prompt: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute RAG query using GraphRAG with configurable retriever.

        Args:
            partition_key: Tenant partition key
            query_text: User query
            search_mode: Retriever mode (vector, hybrid)
            index_name: Vector index name
            top_k: Number of results to retrieve
            prompt: Optional custom prompt template

        Returns:
            Dict with answer and context
        """
        from neo4j_graphrag.generation import GraphRAG
        from neo4j_graphrag.generation.prompts import RagTemplate
        from neo4j_graphrag.retrievers import VectorRetriever, HybridRetriever

        from ..config import Config

        graph_rag = Config.get_graph_rag_util(partition_key)

        retriever = self._build_retriever(graph_rag, search_mode, index_name)
        schema_context = self._load_schema_context(partition_key)
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
            from ...models.repositories import get_repo
            from ...utils.listener import create_listener_info

            logger = self.context.get("logger")
            setting = self.context.get("setting", {})
            info = create_listener_info(
                logger, "rag", setting, partition_key=partition_key
            ) if logger else self.info

            repo = get_repo("request")
            repo.insert_update(
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
        from neo4j_graphrag.retrievers import VectorRetriever, HybridRetriever

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

    def _load_schema_context(self, partition_key: str) -> str:
        """Load the active schema context for RAG enrichment."""
        from ...models.repositories import get_repo

        try:
            repo = get_repo("graph_schema")
            record = repo.resolve_active(partition_key)
            if record and record.get("neo4j_schema_string"):
                return f"\nGraph schema for this tenant:\n{record['neo4j_schema_string']}\n"
        except Exception:
            pass
        return ""


# ---------------------------------------------------------------------------
# Public dispatch functions
# ---------------------------------------------------------------------------


def _search(info: ResolveInfo, **kwargs: Any) -> SearchResult:
    """Private implementation — pure business logic, no telemetry."""
    handler = SearchHandler(info)
    return handler.search(**kwargs)


def dispatch_search(info: ResolveInfo, **kwargs: Any) -> SearchResult:
    """Public dispatch — wraps _search with telemetry."""
    with measure_handler_duration(info, operation="search", handler="search"):
        return _search(info, **kwargs)


def _rag(info: ResolveInfo, **kwargs: Any) -> RAGResult:
    """Private implementation — pure business logic, no telemetry."""
    handler = RAGHandler(info)
    return handler.rag(**kwargs)


def dispatch_rag(info: ResolveInfo, **kwargs: Any) -> RAGResult:
    """Public dispatch — wraps _rag with telemetry."""
    with measure_handler_duration(info, operation="rag", handler="search"):
        return _rag(info, **kwargs)