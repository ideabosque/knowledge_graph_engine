# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

"""
Custom KG Writer for neo4j-graphrag-python.
Subclasses KGWriter abstract class to provide custom MERGE/UPSERT logic.
"""

import logging
from typing import Any, List, Optional

from pydantic import validate_call
from neo4j_graphrag.experimental.components.kg_writer import KGWriter, KGWriterModel
from neo4j_graphrag.experimental.components.types import Neo4jGraph, LexicalGraphConfig

logger = logging.getLogger(__name__)


class CustomNeo4jWriter(KGWriter):
    """
    Custom KG writer using pure Cypher (no APOC dependency).
    Subclasses neo4j_graphrag.KGWriter (abstract base class).

    Uses dynamic label assignment via SET + REMOVE instead of apoc.create.addLabels,
    and per-type MERGE for relationships instead of apoc.merge.relationship.
    """

    def __init__(
        self,
        driver: Any,
        neo4j_database: Optional[str] = None,
        batch_size: int = 1000,
    ):
        self.driver = driver
        self.neo4j_database = neo4j_database or "neo4j"
        self.batch_size = batch_size

    def _db_setup(self) -> None:
        self.driver.execute_query(
            "CREATE INDEX __entity__tmp_internal_id IF NOT EXISTS "
            "FOR (n:__KGBuilder__) ON (n.__tmp_internal_id)",
            database_=self.neo4j_database,
        )

    @validate_call
    async def run(
        self,
        graph: Neo4jGraph,
        lexical_graph_config: LexicalGraphConfig = LexicalGraphConfig(),
    ) -> KGWriterModel:
        try:
            logger.info(
                f"CustomNeo4jWriter.run: {len(graph.nodes)} nodes, "
                f"{len(graph.relationships)} relationships"
            )
            self._db_setup()

            for i in range(0, len(graph.nodes), self.batch_size):
                batch = graph.nodes[i : i + self.batch_size]
                self._upsert_nodes(batch, lexical_graph_config)

            for i in range(0, len(graph.relationships), self.batch_size):
                batch = graph.relationships[i : i + self.batch_size]
                self._upsert_relationships(batch)

            self._db_cleaning()

            return KGWriterModel(
                status="SUCCESS",
                metadata={
                    "node_count": len(graph.nodes),
                    "relationship_count": len(graph.relationships),
                },
            )
        except Exception as e:
            logger.error(f"CustomNeo4jWriter.run FAILED: {e}", exc_info=True)
            return KGWriterModel(
                status="FAILURE",
                metadata={"error": str(e)},
            )

    def _upsert_nodes(
        self, nodes: List, lexical_graph_config: LexicalGraphConfig
    ) -> None:
        if not nodes:
            return

        lexical_labels = set(lexical_graph_config.lexical_graph_node_labels)

        # Group nodes by label set for efficient batching
        label_groups: dict[tuple, list] = {}
        for n in nodes:
            labels = [n.label]
            if n.label not in lexical_labels:
                labels.append("__Entity__")
            key = tuple(sorted(labels))

            row = {"id": n.id, "properties": dict(n.properties)}
            if n.embedding_properties:
                row["embedding_properties"] = {
                    k: list(v) for k, v in n.embedding_properties.items()
                }
            label_groups.setdefault(key, []).append(row)

        for labels, rows in label_groups.items():
            # Build label string: :`Label1`:`Label2`
            label_str = "".join(f":`{l}`" for l in labels)
            query = (
                "UNWIND $rows AS row "
                f"CREATE (n:__KGBuilder__{label_str} "
                "  {__tmp_internal_id: row.id}) "
                "SET n += row.properties "
                "RETURN count(n)"
            )
            self.driver.execute_query(
                query,
                parameters_={"rows": rows},
                database_=self.neo4j_database,
            )

            # Set embedding properties if any rows have them
            emb_rows = [r for r in rows if r.get("embedding_properties")]
            if emb_rows:
                emb_query = (
                    "UNWIND $rows AS row "
                    "MATCH (n:__KGBuilder__ {__tmp_internal_id: row.id}) "
                    "WITH n, row "
                    "UNWIND keys(row.embedding_properties) AS emb "
                    "CALL db.create.setNodeVectorProperty(n, emb, row.embedding_properties[emb]) "
                    "RETURN count(*)"
                )
                self.driver.execute_query(
                    emb_query,
                    parameters_={"rows": emb_rows},
                    database_=self.neo4j_database,
                )

    def _upsert_relationships(self, relationships: List) -> None:
        if not relationships:
            return

        # Group by relationship type for per-type MERGE queries
        type_groups: dict[str, list] = {}
        for rel in relationships:
            row = {
                "start_node_id": rel.start_node_id,
                "end_node_id": rel.end_node_id,
                "properties": dict(rel.properties),
            }
            if rel.embedding_properties:
                row["embedding_properties"] = {
                    k: list(v) for k, v in rel.embedding_properties.items()
                }
            type_groups.setdefault(rel.type, []).append(row)

        for rel_type, rows in type_groups.items():
            rel_type_safe = rel_type.replace("`", "``")
            query = (
                "UNWIND $rows AS row "
                "MATCH (start:__KGBuilder__ {__tmp_internal_id: row.start_node_id}), "
                "      (end:__KGBuilder__ {__tmp_internal_id: row.end_node_id}) "
                f"MERGE (start)-[r:`{rel_type_safe}`]->(end) "
                "SET r += row.properties "
                "RETURN count(r)"
            )
            self.driver.execute_query(
                query,
                parameters_={"rows": rows},
                database_=self.neo4j_database,
            )

            # Set embedding properties if any
            emb_rows = [r for r in rows if r.get("embedding_properties")]
            if emb_rows:
                emb_query = (
                    "UNWIND $rows AS row "
                    "MATCH (start:__KGBuilder__ {__tmp_internal_id: row.start_node_id})"
                    "-[r:`" + rel_type_safe + "`]->"
                    "(end:__KGBuilder__ {__tmp_internal_id: row.end_node_id}) "
                    "WITH r, row "
                    "UNWIND keys(row.embedding_properties) AS emb "
                    "CALL db.create.setRelationshipVectorProperty(r, emb, row.embedding_properties[emb]) "
                    "RETURN count(*)"
                )
                self.driver.execute_query(
                    emb_query,
                    parameters_={"rows": emb_rows},
                    database_=self.neo4j_database,
                )

    def _db_cleaning(self) -> None:
        self.driver.execute_query(
            "MATCH (n:__KGBuilder__) "
            "WHERE n.__tmp_internal_id IS NOT NULL "
            "SET n.__tmp_internal_id = NULL",
            database_=self.neo4j_database,
        )
