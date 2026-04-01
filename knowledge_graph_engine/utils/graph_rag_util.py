# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

try:
    import nest_asyncio
except ImportError:  # pragma: no cover
    nest_asyncio = None

if nest_asyncio is not None:  # pragma: no branch
    nest_asyncio.apply()

from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.experimental.components.schema import (
    GraphSchema,
    SchemaFromTextExtractor,
)
from neo4j_graphrag.experimental.components.kg_writer import KGWriter
from neo4j_graphrag.retrievers import (
    VectorRetriever,
    VectorCypherRetriever,
    Text2CypherRetriever,
    HybridRetriever,
)
from neo4j_graphrag.generation import GraphRAG
from neo4j_graphrag.generation.prompts import RagTemplate
from neo4j_graphrag.indexes import (
    create_vector_index,
    create_fulltext_index,
    drop_index_if_exists,
)
from neo4j_graphrag.embeddings import OpenAIEmbeddings

try:
    from neo4j_graphrag.embeddings import OllamaEmbeddings
except ImportError:  # pragma: no cover
    OllamaEmbeddings = None

logger = logging.getLogger(__name__)


def _suppress_event_loop_closed(loop, context):
    """Suppress 'Event loop is closed' errors from httpx AsyncClient cleanup."""
    exception = context.get("exception")
    if isinstance(exception, RuntimeError) and "Event loop is closed" in str(exception):
        return  # Silently ignore httpx cleanup noise
    loop.default_exception_handler(context)


def _run_async(coro):
    """Run an async coroutine safely from sync context, even inside a running event loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.set_exception_handler(_suppress_event_loop_closed)
    return loop.run_until_complete(coro)


class _SuppressEventLoopClosedFilter(logging.Filter):
    """Filter out 'Event loop is closed' errors from asyncio logger.
    These are harmless GC cleanup noise from httpx.AsyncClient.__del__.
    """
    def filter(self, record):
        if record.exc_info and record.exc_info[1]:
            if "Event loop is closed" in str(record.exc_info[1]):
                return False
        if "Event loop is closed" in record.getMessage():
            return False
        return True


# Apply the filter to the asyncio logger to suppress httpx cleanup noise
logging.getLogger("asyncio").addFilter(_SuppressEventLoopClosedFilter())

try:
    from neo4j_graphrag.llm import (
        AnthropicLLM,
        MistralAILLM,
        OllamaLLM,
        OpenAILLM,
        VertexAILLM,
    )
except ImportError:  # pragma: no cover
    AnthropicLLM = None
    MistralAILLM = None
    OllamaLLM = None
    OpenAILLM = None
    VertexAILLM = None


class GraphRAGUtil:
    """
    GraphRAG operations against a tenant's dedicated Neo4j instance.
    All methods use the exact neo4j-graphrag-python API.
    Uses neo4j_database parameter (not database) per library convention.
    """

    def __init__(self, driver: Any, neo4j_database: str, settings: Dict[str, Any]) -> None:
        self.driver = driver
        self.neo4j_database = neo4j_database
        self.settings = settings
        self.llm = None
        self.embedder = None
        self._init_llm()
        self._init_embedder()

    def _init_llm(self) -> None:
        llm_type = self.settings.get("llm_type", "openai")
        llm_name = self.settings.get("llm_name", "gpt-4o")
        model_params = self.settings.get("llm_model_params", {})

        if llm_type == "openai":
            self.llm = OpenAILLM(
                model_name=llm_name,
                model_params={"top_p": 1, "temperature": 1, **model_params},
                api_key=self.settings.get("openai_api_key"),
                base_url=self.settings.get("openai_base_url"),
            )
        elif llm_type == "anthropic":
            self.llm = AnthropicLLM(
                model_name=llm_name,
                model_params={"max_tokens": 4096, **model_params},
                api_key=self.settings.get("anthropic_api_key"),
                base_url=self.settings.get("anthropic_base_url"),
            )
        elif llm_type == "ollama":
            self.llm = OllamaLLM(
                model_name=llm_name,
                model_params=model_params or None,
                host=self.settings.get("ollama_host", "http://localhost:11434"),
            )
        elif llm_type == "vertexai":
            self.llm = VertexAILLM(
                model_name=llm_name,
                model_params=model_params or None,
                system_instruction=self.settings.get("vertexai_system_instruction"),
            )
        elif llm_type == "mistralai":
            self.llm = MistralAILLM(
                model_name=llm_name,
                model_params=model_params or None,
                api_key=self.settings.get("mistralai_api_key"),
            )
        else:
            raise ValueError(f"Unsupported LLM type: {llm_type}")

    def _init_embedder(self) -> None:
        embedding_provider = self.settings.get("embedding_provider", self.settings.get("llm_type", "openai"))
        embedding_model = self.settings.get("embedding_model", "text-embedding-3-small")

        if embedding_provider == "ollama":
            if OllamaEmbeddings is None:
                raise ValueError(
                    "embedding_provider='ollama' requires neo4j-graphrag[ollama] extras. "
                    "Install with: pip install 'neo4j-graphrag[ollama]'"
                )
            self.embedder = OllamaEmbeddings(
                model=embedding_model,
                host=self.settings.get("ollama_host", "http://localhost:11434"),
            )
        else:
            self.embedder = OpenAIEmbeddings(
                model=embedding_model,
                api_key=self.settings.get("openai_api_key"),
                base_url=self.settings.get("openai_base_url"),
            )

    def build_knowledge_graph(
        self,
        text: str,
        schema: Union[GraphSchema, dict, str, None] = None,
        kg_writer: Optional[KGWriter] = None,
        on_error: str = "IGNORE",
        perform_entity_resolution: bool = False,
    ) -> Any:
        """
        Extract entities/relationships and store in tenant's Neo4j.

        Args:
            text: Document text to extract from
            schema: GraphSchema object, dict shorthand, "EXTRACTED", "FREE", or None
            kg_writer: Custom KGWriter subclass (defaults to Neo4jWriter)
            on_error: "RAISE" or "IGNORE"
        """
        if kg_writer is None:
            from .neo4j_writer import CustomNeo4jWriter
            kg_writer = CustomNeo4jWriter(
                driver=self.driver,
                neo4j_database=self.neo4j_database,
            )

        pipeline = SimpleKGPipeline(
            llm=self.llm,
            driver=self.driver,
            embedder=self.embedder,
            schema=schema,
            from_pdf=False,
            neo4j_database=self.neo4j_database,
            kg_writer=kg_writer,
            on_error=on_error,
            perform_entity_resolution=perform_entity_resolution,
        )

        return _run_async(pipeline.run_async(text=text))

    def build_schema_from_text(self, text: str) -> GraphSchema:
        """Auto-generate GraphSchema from text using SchemaFromTextExtractor."""
        extractor = SchemaFromTextExtractor(llm=self.llm)
        return _run_async(extractor.run(text=text))

    def vector_search(
        self,
        query_text: str,
        index_name: str = "vector",
        filters: Optional[dict] = None,
        top_k: int = 5,
    ) -> Any:
        """Semantic similarity search on embeddings."""
        retriever = VectorRetriever(
            driver=self.driver,
            index_name=index_name,
            embedder=self.embedder,
            neo4j_database=self.neo4j_database,
        )
        return retriever.search(query_text=query_text, top_k=top_k, filters=filters)

    def text2cypher_search(
        self,
        query_text: str,
        neo4j_schema: Optional[str] = None,
        top_k: int = 10,
    ) -> Any:
        """
        LLM converts natural language to Cypher.
        If neo4j_schema is None, auto-fetches from tenant's Neo4j instance.
        """
        retriever = Text2CypherRetriever(
            driver=self.driver,
            llm=self.llm,
            neo4j_schema=neo4j_schema,
            neo4j_database=self.neo4j_database,
        )
        return retriever.search(query_text=query_text)

    def vector_cypher_search(
        self,
        query_text: str,
        index_name: str = "vector",
        retrieval_query: str = "RETURN node, score",
        top_k: int = 5,
    ) -> Any:
        """Vector search + custom Cypher traversal."""
        retriever = VectorCypherRetriever(
            driver=self.driver,
            index_name=index_name,
            retrieval_query=retrieval_query,
            embedder=self.embedder,
            neo4j_database=self.neo4j_database,
        )
        return retriever.search(query_text=query_text, top_k=top_k)

    def hybrid_search(
        self,
        query_text: str,
        vector_index_name: str = "vector",
        fulltext_index_name: str = "fulltext",
        top_k: int = 5,
    ) -> Any:
        """Combined vector + fulltext search."""
        retriever = HybridRetriever(
            driver=self.driver,
            vector_index_name=vector_index_name,
            fulltext_index_name=fulltext_index_name,
            embedder=self.embedder,
            neo4j_database=self.neo4j_database,
        )
        return retriever.search(query_text=query_text, top_k=top_k)

    def create_vector_index(
        self,
        index_name: str = "vector",
        label: str = "Chunk",
        embedding_property: str = "embedding",
    ) -> None:
        """Create vector index in this tenant's Neo4j instance."""
        drop_index_if_exists(
            self.driver, index_name, neo4j_database=self.neo4j_database
        )
        create_vector_index(
            self.driver,
            index_name,
            label=label,
            embedding_property=embedding_property,
            dimensions=self.settings.get("dimension", 1536),
            similarity_fn="cosine",
            neo4j_database=self.neo4j_database,
        )

    def create_fulltext_index(
        self,
        index_name: str = "fulltext",
        label: str = "Chunk",
        node_properties: Optional[List[str]] = None,
    ) -> None:
        """Create fulltext index in this tenant's Neo4j instance."""
        create_fulltext_index(
            self.driver,
            index_name,
            label=label,
            node_properties=node_properties or ["text"],
            neo4j_database=self.neo4j_database,
        )

    def close(self) -> None:
        if self.driver:
            self.driver.close()
