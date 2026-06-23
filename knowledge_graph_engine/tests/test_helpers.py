# -*- coding: utf-8 -*-
"""
Tests for helper utilities.
"""
from __future__ import print_function

__author__ = "silvaengine"

import pytest
from unittest.mock import MagicMock


class TestNormalization:
    """Test normalization utilities."""

    @pytest.mark.unit
    def test_normalize_to_json_with_decimal(self):
        """Test normalization handles Decimal."""
        from decimal import Decimal
        from knowledge_graph_engine.utils.normalization import normalize_to_json

        class MockObj:
            attribute_values = {"value": Decimal("10.5"), "int_val": Decimal("5")}

        result = normalize_to_json(MockObj())
        assert result["value"] == 10.5
        assert result["int_val"] == 5

    @pytest.mark.unit
    def test_normalize_to_json_with_dict(self):
        """Test normalization handles dict input."""
        from knowledge_graph_engine.utils.normalization import normalize_to_json

        result = normalize_to_json({"key": "value"})
        assert result == {"key": "value"}

    @pytest.mark.unit
    def test_normalize_to_json_with_none(self):
        """Test normalization handles None."""
        from knowledge_graph_engine.utils.normalization import normalize_to_json

        result = normalize_to_json(None)
        assert result == {}


class TestListener:
    """Test listener utilities."""

    @pytest.mark.unit
    def test_create_listener_info(self, mock_logger):
        """Test listener info creation."""
        from knowledge_graph_engine.utils.listener import create_listener_info

        setting = {"region": "us-east-1"}
        info = create_listener_info(
            mock_logger,
            "extract",
            setting,
            partition_key="ep001#partA",
        )

        assert info.context["partition_key"] == "ep001#partA"
        assert info.context["setting"] == setting
        assert info.field_name == "extract"


class TestParseFile:
    """Test file parsing utilities."""

    @pytest.mark.unit
    def test_parse_csv(self):
        """Test CSV parsing."""
        from knowledge_graph_engine.utils.parse_file import parse_csv

        csv_content = "name,age\nJohn,30\nJane,25"
        result = parse_csv(csv_content)

        assert len(result) == 2
        assert result[0]["name"] == "John"
        assert result[0]["age"] == "30"
        assert result[1]["name"] == "Jane"

    @pytest.mark.unit
    def test_parse_csv_with_custom_delimiter(self):
        """Test CSV parsing with custom delimiter."""
        from knowledge_graph_engine.utils.parse_file import parse_csv

        csv_content = "name;age\nJohn;30\nJane;25"
        result = parse_csv(csv_content, delimiter=";")

        assert len(result) == 2
        assert result[0]["name"] == "John"