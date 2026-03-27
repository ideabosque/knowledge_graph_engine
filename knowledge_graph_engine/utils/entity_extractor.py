# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

"""
Custom entity extraction utility for fallback scenarios.
Primary extraction is handled by SimpleKGPipeline from neo4j-graphrag-python.
This module provides:
1. Fallback extraction when LLM is unavailable
2. Custom ID resolution for entities
3. Entity deduplication logic
"""

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from neo4j_graphrag.experimental.components.schema import (
    GraphSchema,
    NodeType,
    PropertyType,
)


class EntityExtractor:
    """
    Custom entity extraction for fallback scenarios.
    Use SimpleKGPipeline for primary extraction with LLM.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        llm_model: str = "gpt-4",
        llm_provider: str = "openai",
    ):
        self.llm = llm
        self.llm_model = llm_model
        self.llm_provider = llm_provider

    def extract(
        self, text: str, schema: GraphSchema
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extract entities and relationships from text using GraphSchema.

        Args:
            text: Document text
            schema: GraphSchema object from neo4j-graphrag-python

        Returns:
            Tuple of (entities, relationships) as dicts
        """
        if not self.llm:
            return self._extract_fallback(text, schema)

        # Convert GraphSchema to legacy format for prompting
        schema_dict = self._schema_to_dict(schema)
        
        entities_prompt = self._build_entity_prompt(text, schema_dict)
        entities = self._parse_entities(entities_prompt)

        relationships_prompt = self._build_relationship_prompt(
            text, entities, schema_dict
        )
        relationships = self._parse_relationships(relationships_prompt)

        return entities, relationships

    def _schema_to_dict(self, schema: GraphSchema) -> Dict[str, Any]:
        """Convert GraphSchema to legacy dict format for prompting."""
        node_types = []
        for nt in (schema.node_types or []):
            if isinstance(nt, str):
                node_types.append({"label": nt, "properties": []})
            else:
                node_types.append({
                    "label": nt.label,
                    "description": nt.description or "",
                    "properties": [
                        {"name": p.name, "type": p.type, "required": p.required}
                        for p in (nt.properties or [])
                    ],
                })

        relationship_types = []
        for rt in (schema.relationship_types or []):
            if isinstance(rt, str):
                relationship_types.append({"type": rt})
            else:
                relationship_types.append({
                    "type": rt.label,
                    "description": rt.description or "",
                })

        patterns = []
        for p in (schema.patterns or []):
            patterns.append({
                "start": p[0],
                "type": p[1],
                "end": p[2],
            })

        return {
            "entities": node_types,
            "relationships": relationship_types,
            "patterns": patterns,
        }

    def _build_entity_prompt(self, text: str, schema: dict) -> str:
        """Build prompt for entity extraction."""
        entity_types = []
        for entity in schema.get("entities", []):
            label = entity.get("label", "Entity")
            desc = entity.get("description", "")
            props = ", ".join([p["name"] for p in entity.get("properties", [])])
            entity_types.append(f"- {label}: {desc}. Properties: {props}")

        entity_types_str = "\n".join(entity_types) if entity_types else "No specific entities defined"

        return f"""Extract entities from the following text. Return a JSON array of entities.
Each entity must have: id, label, and properties matching the schema.

Schema entity types:
{entity_types_str}

Text to analyze:
{text[:4000]}

Return a JSON array like:
[
  {{"id": "entity1", "label": "Company", "properties": {{"name": "Acme", "industry": "Tech"}}}},
  {{"id": "entity2", "label": "Person", "properties": {{"name": "John"}}}}
]"""

    def _build_relationship_prompt(
        self, text: str, entities: List[dict], schema: dict
    ) -> str:
        """Build prompt for relationship extraction."""
        rel_types = []
        for rel in schema.get("relationships", []):
            rel_types.append(f"- {rel.get('type', 'RELATED')}: {rel.get('description', '')}")

        rel_types_str = "\n".join(rel_types) if rel_types else "No specific relationships defined"
        entity_str = ", ".join([f"{e['label']}:{e['id']}" for e in entities])

        return f"""Extract relationships between entities. Return a JSON array of relationships.
Each relationship must have: type, start_id, end_id.

Schema relationship types:
{rel_types_str}

Entities found:
{entity_str}

Text to analyze:
{text[:4000]}

Return a JSON array like:
[
  {{"type": "WORKS_AT", "start_id": "entity2", "end_id": "entity1"}}
]"""

    def _parse_entities(self, prompt: str) -> List[dict]:
        """Parse entity extraction response."""
        try:
            if self.llm_provider == "anthropic":
                response = self.llm.messages.create(
                    model=self.llm_model,
                    max_tokens=4000,
                    messages=[{"role": "user", "content": prompt}],
                )
                entities_text = response.content[0].text
            else:
                response = self.llm.chat.completions.create(
                    model=self.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                entities_text = response.choices[0].message.content

            entities = json.loads(entities_text)
            for entity in entities:
                if "id" not in entity or not entity["id"]:
                    entity["id"] = self._generate_entity_id(
                        entity.get("label", "Entity"),
                        entity.get("properties", {}),
                    )
            return entities
        except Exception:
            return []

    def _parse_relationships(self, prompt: str) -> List[dict]:
        """Parse relationship extraction response."""
        try:
            if self.llm_provider == "anthropic":
                response = self.llm.messages.create(
                    model=self.llm_model,
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}],
                )
                rels_text = response.content[0].text
            else:
                response = self.llm.chat.completions.create(
                    model=self.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                rels_text = response.choices[0].message.content

            return json.loads(rels_text)
        except Exception:
            return []

    def _extract_fallback(
        self, text: str, schema: GraphSchema
    ) -> Tuple[List[dict], List[dict]]:
        """Fallback extraction without LLM using regex patterns."""
        entities = []
        relationships = []
        schema_dict = self._schema_to_dict(schema)

        for entity_def in schema_dict.get("entities", []):
            label = entity_def.get("label", "Entity")
            unique_field = None
            for prop in entity_def.get("properties", []):
                if prop.get("required"):
                    unique_field = prop["name"]
                    break

            if unique_field:
                pattern = rf"{unique_field}[:\s]+([A-Z][a-zA-Z\s]+)"
                matches = re.findall(pattern, text)
                for match in matches:
                    entity_id = self._generate_entity_id(label, {unique_field: match})
                    entities.append({
                        "id": entity_id,
                        "label": label,
                        "properties": {unique_field: match},
                    })

        return entities, relationships

    def _generate_entity_id(self, label: str, properties: dict) -> str:
        """Generate a deterministic entity ID from label and properties."""
        prop_str = json.dumps(properties, sort_keys=True)
        hash_str = hashlib.md5(f"{label}:{prop_str}".encode()).hexdigest()[:8]
        return f"{label.lower()}-{hash_str}"