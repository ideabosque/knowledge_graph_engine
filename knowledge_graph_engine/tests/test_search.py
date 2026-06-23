# -*- coding: utf-8 -*-
"""
Tests for search and RAG functionality.
"""
from __future__ import print_function
import sys

__author__ = "silvaengine"

import pytest
from unittest.mock import MagicMock, patch


class TestSearch:
    """Test search functionality."""

    @pytest.mark.unit
    def test_resolve_search_vector(self, mock_info):
        """Test vector search resolution."""
        with patch("knowledge_graph_engine.handlers.config.Config.get_graph_rag_util") as mock_util:
            mock_rag = MagicMock()
            mock_rag.vector_search.return_value = [{"text": "test", "score": 0.9}]
            mock_util.return_value = mock_rag

            from knowledge_graph_engine.queries.search import resolve_search

            result = resolve_search(mock_info, query_text="test query", search_mode="vector")
            assert "results" in result


class TestRAG:
    """Test RAG functionality."""

    @pytest.mark.unit
    def test_resolve_rag(self, mock_info):
        """Test RAG resolution."""
        from types import SimpleNamespace

        with patch("knowledge_graph_engine.handlers.config.Config.get_graph_rag_util") as mock_util, \
             patch("knowledge_graph_engine.handlers.rag_handler.VectorRetriever") as mock_vr_cls, \
             patch("knowledge_graph_engine.handlers.rag_handler.GraphRAG") as mock_graphrag_cls:

            mock_rag_util = MagicMock()
            mock_util.return_value = mock_rag_util

            mock_retriever = MagicMock()
            mock_vr_cls.return_value = mock_retriever

            mock_graphrag = MagicMock()
            mock_graphrag.search.return_value = SimpleNamespace(
                answer="test answer", retriever_result=[]
            )
            mock_graphrag_cls.return_value = mock_graphrag

            from knowledge_graph_engine.queries.search import resolve_rag

            result = resolve_rag(mock_info, query_text="test query")
            assert "answer" in result
            assert result["answer"] == "test answer"

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"] + sys.argv[1:]))
