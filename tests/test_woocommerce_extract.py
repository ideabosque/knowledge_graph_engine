# -*- coding: utf-8 -*-
"""
Integration test: Load WooCommerce products and extract knowledge graph.

Fetches products from a WooCommerce store via REST API (using requests),
converts them to structured text, and feeds them to the executeExtract
mutation to build a knowledge graph in the tenant's Neo4j instance.

Requirements:
    - WooCommerce REST API credentials in .env
    - Neo4j instance registered for the tenant partition

Run with: pytest tests/test_woocommerce_extract.py -m integration -v -s
"""
from __future__ import print_function

__author__ = "silvaengine"

import json
import os

import pytest
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

from .conftest import SETTING

# WooCommerce settings from .env
WC_URL = os.getenv("WOOCOMMERCE_URL", "").rstrip("/")
WC_CONSUMER_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET")


def fetch_products(per_page: int = 10, page: int = 1) -> list:
    """Fetch products from WooCommerce REST API."""
    url = f"{WC_URL}/products"
    response = requests.get(
        url,
        params={"per_page": per_page, "page": page},
        auth=HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def product_to_text(product: dict) -> str:
    """Convert a WooCommerce product to structured text for extraction."""
    lines = []

    lines.append(f"Product: {product.get('name', 'Unknown')}")
    lines.append(f"SKU: {product.get('sku', 'N/A')}")
    lines.append(f"Type: {product.get('type', 'simple')}")
    lines.append(f"Status: {product.get('status', 'draft')}")
    lines.append(
        f"Price: {product.get('price', '0')} "
        f"(Regular: {product.get('regular_price', '0')}, "
        f"Sale: {product.get('sale_price', '')})"
    )

    if product.get("short_description"):
        desc = product["short_description"].replace("<p>", "").replace("</p>", "").strip()
        lines.append(f"Short Description: {desc}")

    if product.get("description"):
        desc = (
            product["description"]
            .replace("<p>", "")
            .replace("</p>", "")
            .replace("<br />", " ")
            .strip()
        )
        if len(desc) > 2000:
            desc = desc[:2000] + "..."
        lines.append(f"Description: {desc}")

    categories = product.get("categories", [])
    if categories:
        cat_names = [c.get("name", "") for c in categories]
        lines.append(f"Categories: {', '.join(cat_names)}")

    tags = product.get("tags", [])
    if tags:
        tag_names = [t.get("name", "") for t in tags]
        lines.append(f"Tags: {', '.join(tag_names)}")

    for attr in product.get("attributes", []):
        attr_name = attr.get("name", "")
        options = attr.get("options", [])
        if options:
            lines.append(f"Attribute {attr_name}: {', '.join(options)}")

    if product.get("weight"):
        lines.append(f"Weight: {product['weight']}")
    dimensions = product.get("dimensions", {})
    if dimensions.get("length") or dimensions.get("width") or dimensions.get("height"):
        lines.append(
            f"Dimensions: {dimensions.get('length', '')}x"
            f"{dimensions.get('width', '')}x{dimensions.get('height', '')}"
        )

    lines.append(f"In Stock: {product.get('in_stock', True)}")
    if product.get("stock_quantity") is not None:
        lines.append(f"Stock Quantity: {product['stock_quantity']}")

    related = product.get("related_ids", [])
    if related:
        lines.append(f"Related Product IDs: {', '.join(str(r) for r in related)}")
    upsells = product.get("upsell_ids", [])
    if upsells:
        lines.append(f"Upsell Product IDs: {', '.join(str(u) for u in upsells)}")
    cross_sells = product.get("cross_sell_ids", [])
    if cross_sells:
        lines.append(f"Cross-sell Product IDs: {', '.join(str(c) for c in cross_sells)}")

    return "\n".join(lines)


EXTRACT_MUTATION = """
    mutation(
        $text: String!,
        $documentSource: String,
        $documentExternalId: String
    ) {
        executeExtract(
            text: $text,
            documentSource: $documentSource,
            documentExternalId: $documentExternalId
        ) {
            status
            partitionKey
            documentUuid
            schemaName
            entitiesExtracted
            relationshipsExtracted
        }
    }
"""


@pytest.mark.integration
class TestWooCommerceExtract:
    """Load WooCommerce products and extract into knowledge graph."""

    @pytest.fixture(autouse=True)
    def _check_wc_credentials(self):
        if not all([WC_URL, WC_CONSUMER_KEY, WC_CONSUMER_SECRET]):
            pytest.skip("WooCommerce credentials not set in .env")

    def test_extract_products(self, engine):
        """Fetch WooCommerce products and extract knowledge graph."""
        endpoint_id = SETTING.get("endpoint_id")
        part_id = SETTING.get("part_id")

        products = fetch_products(per_page=10, page=1)
        assert len(products) > 0, "No products found in WooCommerce store"

        print(f"\nFetched {len(products)} products from {WC_URL}")

        results = []
        for product in products:
            text = product_to_text(product)
            print(f"\n--- Extracting: {product.get('name')} (ID: {product.get('id')}) ---")

            variables = {
                "text": text,
                "documentSource": "woocommerce:product",
                "documentExternalId": str(product.get("id", "")),
            }

            result = engine.knowledge_graph_engine_graphql(
                query=EXTRACT_MUTATION,
                variables=variables,
                endpoint_id=endpoint_id,
                part_id=part_id,
            )

            assert result is not None
            body = result.get("body")
            if isinstance(body, str):
                body = json.loads(body)

            if result.get("statusCode") == 200:
                data = body["data"]["executeExtract"]
                print(
                    f"  Status: {data['status']}, "
                    f"Entities: {data['entitiesExtracted']}, "
                    f"Relationships: {data['relationshipsExtracted']}, "
                    f"Document: {data['documentUuid']}"
                )
                results.append(data)
            else:
                print(f"  ERROR: {body.get('errors', 'Unknown error')}")

        assert len(results) > 0, "No products were successfully extracted"
        print(f"\nSuccessfully extracted {len(results)} products into knowledge graph")
