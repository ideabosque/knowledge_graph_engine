# -*- coding: utf-8 -*-
"""
Integration tests: Search and RAG queries against the knowledge graph.

Assumes WooCommerce products have been extracted into Neo4j
(via test_woocommerce_extract.py) and a vector index exists.

Run with: pytest tests/test_search_rag.py -m integration -v -s
"""
from __future__ import print_function

__author__ = "silvaengine"

import json
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

from .conftest import SETTING

SEARCH_QUERY = """
    query(
        $queryText: String!,
        $searchMode: String,
        $indexName: String,
        $topK: Int,
        $page: Int,
        $limit: Int
    ) {
        search(
            queryText: $queryText,
            searchMode: $searchMode,
            indexName: $indexName,
            topK: $topK,
            page: $page,
            limit: $limit
        ) {
            results
            query
            total
            page
            limit
        }
    }
"""

RAG_QUERY = """
    query(
        $queryText: String!,
        $searchMode: String,
        $indexName: String,
        $topK: Int,
        $prompt: String
    ) {
        rag(
            queryText: $queryText,
            searchMode: $searchMode,
            indexName: $indexName,
            topK: $topK,
            prompt: $prompt
        ) {
            answer
            sources
            context
        }
    }
"""

TEXT2CYPHER_QUERY = """
    query(
        $queryText: String!,
        $searchMode: String,
        $schemaName: String,
        $topK: Int
    ) {
        search(
            queryText: $queryText,
            searchMode: $searchMode,
            schemaName: $schemaName,
            topK: $topK
        ) {
            results
            query
            total
            page
            limit
        }
    }
"""


def _parse_body(result):
    """Parse response body from engine result."""
    body = result.get("body")
    if isinstance(body, str):
        body = json.loads(body)
    return body


@pytest.mark.integration
class TestSearchSetup:
    """Create vector index needed by search tests."""

    def test_create_vector_index(self, engine):
        """Create vector index on Chunk nodes for search."""
        from knowledge_graph_engine.handlers.partition_manager import PartitionManager
        from knowledge_graph_engine.handlers.config import Config

        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")
        partition_key = PartitionManager.build_partition_key(endpoint_id, part_id)

        graph_rag = Config.get_graph_rag_util(partition_key)
        graph_rag.create_vector_index(
            index_name="vector",
            label="Chunk",
            embedding_property="embedding",
        )

        print("\nVector index 'vector' created on Chunk.embedding")

        # Verify the index was created
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            SETTING.get("neo4j_uri"),
            auth=(SETTING.get("neo4j_username"), SETTING.get("neo4j_password")),
        )
        with driver.session(database=SETTING.get("neo4j_database", "neo4j")) as session:
            result = session.run(
                "SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name"
            )
            indexes = [r["name"] for r in result]
        driver.close()

        assert "vector" in indexes, f"Vector index not found. Indexes: {indexes}"
        print(f"Verified vector index exists: {indexes}")

    def test_create_fulltext_index(self, engine):
        """Create fulltext index on Chunk nodes for hybrid search."""
        from knowledge_graph_engine.handlers.partition_manager import PartitionManager
        from knowledge_graph_engine.handlers.config import Config

        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")
        partition_key = PartitionManager.build_partition_key(endpoint_id, part_id)

        graph_rag = Config.get_graph_rag_util(partition_key)
        graph_rag.create_fulltext_index(
            index_name="fulltext",
            label="Chunk",
            node_properties=["text"],
        )

        print("\nFulltext index 'fulltext' created on Chunk.text")


@pytest.mark.integration
class TestVectorSearch:
    """Test vector similarity search."""

    def test_vector_search_products(self, engine):
        """Search for products using vector similarity."""
        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")

        result = engine.knowledge_graph_engine_graphql(
            query=SEARCH_QUERY,
            variables={
                "queryText": "snowboard products for winter sports",
                "searchMode": "vector",
                "indexName": "vector",
                "topK": 5,
                "page": 1,
                "limit": 5,
            },
            endpoint_id=endpoint_id,
            part_id=part_id,
        )

        assert result is not None
        body = _parse_body(result)

        if result.get("statusCode") == 200:
            data = body["data"]["search"]
            print(f"\nVector Search Results:")
            print(f"  Total: {data['total']}")
            print(f"  Page: {data['page']}, Limit: {data['limit']}")
            for i, item in enumerate(data.get("results") or []):
                content = str(item)[:120] if item else "N/A"
                print(f"  [{i+1}] {content}...")
            assert data["total"] > 0, "Expected at least one search result"
        else:
            errors = body.get("errors", [])
            print(f"\nSearch returned errors: {errors}")
            pytest.fail(f"Search failed with status {result.get('statusCode')}: {errors}")

    def test_vector_search_safety_gear(self, engine):
        """Search for safety equipment products."""
        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")

        result = engine.knowledge_graph_engine_graphql(
            query=SEARCH_QUERY,
            variables={
                "queryText": "safety glasses protective equipment",
                "searchMode": "vector",
                "indexName": "vector",
                "topK": 3,
            },
            endpoint_id=endpoint_id,
            part_id=part_id,
        )

        assert result is not None
        body = _parse_body(result)

        if result.get("statusCode") == 200:
            data = body["data"]["search"]
            print(f"\nSafety Gear Search: {data['total']} results")
            for i, item in enumerate(data.get("results") or []):
                content = str(item)[:120] if item else "N/A"
                print(f"  [{i+1}] {content}...")
        else:
            errors = body.get("errors", [])
            pytest.fail(f"Search failed: {errors}")


@pytest.mark.integration
class TestText2CypherSearch:
    """Test text-to-Cypher search."""

    def test_text2cypher_search(self, engine):
        """Search using LLM-generated Cypher queries."""
        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")

        result = engine.knowledge_graph_engine_graphql(
            query=TEXT2CYPHER_QUERY,
            variables={
                "queryText": "What products are sold by NEProdAI?",
                "searchMode": "text2cypher",
                "topK": 10,
            },
            endpoint_id=endpoint_id,
            part_id=part_id,
        )

        assert result is not None
        body = _parse_body(result)

        if result.get("statusCode") == 200:
            data = body["data"]["search"]
            print(f"\nText2Cypher Search Results:")
            print(f"  Total: {data['total']}")
            for i, item in enumerate(data.get("results") or []):
                content = str(item)[:150] if item else "N/A"
                print(f"  [{i+1}] {content}...")
        else:
            errors = body.get("errors", [])
            print(f"\nText2Cypher errors (may be expected without schema): {errors}")


@pytest.mark.integration
class TestRAG:
    """Test RAG (Retrieval Augmented Generation) queries."""

    def test_rag_query(self, engine):
        """Ask a question using RAG over the knowledge graph."""
        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")

        result = engine.knowledge_graph_engine_graphql(
            query=RAG_QUERY,
            variables={
                "queryText": "What snowboard products are available and what are their prices?",
                "searchMode": "vector",
                "indexName": "vector",
                "topK": 5,
            },
            endpoint_id=endpoint_id,
            part_id=part_id,
        )

        assert result is not None
        body = _parse_body(result)

        if result.get("statusCode") == 200:
            data = body["data"]["rag"]
            print(f"\nRAG Answer:")
            print(f"  {data['answer']}")
            print(f"\n  Context items: {len(data.get('context') or [])}")
            assert data["answer"], "Expected a non-empty RAG answer"
        else:
            errors = body.get("errors", [])
            print(f"\nRAG errors: {errors}")
            pytest.fail(f"RAG failed with status {result.get('statusCode')}: {errors}")

    def test_rag_with_custom_prompt(self, engine):
        """RAG query with a custom prompt template."""
        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")

        result = engine.knowledge_graph_engine_graphql(
            query=RAG_QUERY,
            variables={
                "queryText": "What work gloves are available?",
                "searchMode": "vector",
                "indexName": "vector",
                "topK": 3,
                "prompt": (
                    "Based on the following context from a product catalog, "
                    "answer the question concisely.\n\n"
                    "Context:\n{context}\n\n"
                    "Examples:\n{examples}\n\n"
                    "Question: {query_text}\n"
                    "Answer:"
                ),
            },
            endpoint_id=endpoint_id,
            part_id=part_id,
        )

        assert result is not None
        body = _parse_body(result)

        if result.get("statusCode") == 200:
            data = body["data"]["rag"]
            print(f"\nRAG (custom prompt) Answer:")
            print(f"  {data['answer']}")
            print(f"  Context items: {len(data.get('context') or [])}")
            assert data["answer"], "Expected a non-empty RAG answer"
        else:
            errors = body.get("errors", [])
            pytest.fail(f"RAG custom prompt failed: {errors}")
