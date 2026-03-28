# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import traceback
import uuid
from typing import Any, Dict, Optional

import pendulum


class Extractor:
    """
    Knowledge graph extraction handler.
    Uses SimpleKGPipeline from neo4j-graphrag-python for extraction.
    """

    def __init__(self, info: Dict[str, Any]):
        self.info = info
        context = info.context if hasattr(info, "context") else {}
        self.logger = context.get("logger")
        self.setting = context.get("setting", {})

    def extract(self, **params: Any) -> Dict[str, Any]:
        """
        Extract knowledge graph from document text.

        Args:
            params: Extraction parameters
                - partition_key: Tenant partition key (required)
                - text: Document text to extract from (required)
                - graph_schema: Optional GraphSchema, dict, or "EXTRACTED"/"FREE"/"FROM_GRAPH"
                - document_source: Optional document source identifier
                - document_external_id: Optional external document ID

        Returns:
            dict with extraction results including document_uuid
        """
        partition_key = params.get("partition_key")
        text = params.get("text", "")
        graph_schema = params.get("graph_schema")
        document_source = params.get("document_source", "unknown")
        document_external_id = params.get("document_external_id")

        if not partition_key:
            raise ValueError("partition_key is required")

        if not text:
            raise ValueError("text is required")

        from ..handlers.config import Config
        from ..handlers.schema_resolver import SchemaResolver
        from ..models.document import insert_update_document

        # Get tenant's GraphRAG utility
        graph_rag_util = Config.get_graph_rag_util(partition_key)

        # Resolve schema (active schema, user-provided, or auto-generate)
        schema_resolver = SchemaResolver(graph_rag_util, partition_key)
        resolved_schema = schema_resolver.resolve(
            text=text,
            graph_schema=graph_schema,
        )

        # Extract entities and relationships using SimpleKGPipeline
        try:
            extraction_result = graph_rag_util.build_knowledge_graph(
                text=text,
                schema=resolved_schema,
            )
        except Exception as e:
            if self.logger:
                self.logger.error(f"Extraction failed: {traceback.format_exc()}")

            # Fallback: use EntityExtractor for extraction without the full pipeline
            extraction_result = self._extract_fallback(
                text=text,
                schema=resolved_schema,
                graph_rag_util=graph_rag_util,
            )

            if extraction_result is None:
                # Record error to DynamoDB for observability
                self._record_process_error(
                    partition_key=partition_key,
                    document_source=document_source,
                    document_external_id=document_external_id,
                    error_message=str(e),
                )
                raise RuntimeError(f"Knowledge graph extraction failed: {e}") from e

        # Persist document metadata to DynamoDB
        document_uuid = f"doc-{pendulum.now('UTC').int_timestamp}-{uuid.uuid4().hex[:8]}"
        from .partition_manager import PartitionManager

        parsed_endpoint, parsed_part = PartitionManager.parse_partition_key(partition_key)
        endpoint_id = params.get("endpoint_id") or parsed_endpoint
        part_id = params.get("part_id") or parsed_part

        # Ensure info.context carries endpoint_id/part_id for model decorators
        if hasattr(self.info, "context"):
            self.info.context.setdefault("endpoint_id", endpoint_id)
            self.info.context.setdefault("part_id", part_id)

        try:
            insert_update_document(
                self.info,
                partition_key=partition_key,
                document_uuid=document_uuid,
                document_source=document_source,
                document_external_id=document_external_id,
                content=text[:10000],  # Store truncated content
                status="processed",
                updated_by="extractor",
            )
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to persist document metadata: {e}")

        # Extract counts from PipelineResult
        entities_count = 0
        relationships_count = 0

        if hasattr(extraction_result, "result"):
            # PipelineResult.result is a dict: {"writer": {"status": ..., "metadata": {...}}}
            pipeline_data = extraction_result.result
            if isinstance(pipeline_data, dict):
                writer_data = pipeline_data.get("writer", {})
                if isinstance(writer_data, dict):
                    metadata = writer_data.get("metadata", {})
                    entities_count = metadata.get("node_count", 0)
                    relationships_count = metadata.get("relationship_count", 0)
        elif isinstance(extraction_result, dict):
            entities_count = extraction_result.get("entities_count", 0)
            relationships_count = extraction_result.get("relationships_count", 0)

        return {
            "status": "success",
            "partition_key": partition_key,
            "document_uuid": document_uuid,
            "schema_name": "active",
            "entities_extracted": entities_count,
            "relationships_extracted": relationships_count,
            "result": extraction_result,
        }

    def _extract_fallback(
        self,
        text: str,
        schema: Any,
        graph_rag_util: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Fallback extraction using EntityExtractor when SimpleKGPipeline fails.
        Returns a dict with entities/relationships or None if fallback also fails.
        """
        try:
            from ..utils.entity_extractor import EntityExtractor

            extractor = EntityExtractor(llm=graph_rag_util.llm)
            entities, relationships = extractor.extract(text=text, schema=schema)

            if self.logger:
                self.logger.info(
                    f"Fallback extraction: {len(entities)} entities, "
                    f"{len(relationships)} relationships"
                )

            return {
                "entities_count": len(entities),
                "relationships_count": len(relationships),
                "entities": entities,
                "relationships": relationships,
            }
        except Exception as fallback_err:
            if self.logger:
                self.logger.warning(f"Fallback extraction also failed: {fallback_err}")
            return None

    def _record_process_error(
        self,
        partition_key: str,
        document_source: str,
        document_external_id: str = None,
        error_message: str = "",
    ) -> None:
        """Persist extraction error to kge-document_process_errors for observability."""
        try:
            from ..models.document_process_error import insert_update_document_process_error

            insert_update_document_process_error(
                self.info,
                partition_key=partition_key,
                document_source=document_source,
                document_external_id=document_external_id,
                error_message=error_message[:10000],  # Truncate for DynamoDB
                process_status="failed",
            )
        except Exception:
            if self.logger:
                self.logger.warning("Failed to record process error to DynamoDB")
