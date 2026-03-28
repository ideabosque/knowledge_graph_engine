from __future__ import annotations

import sys
import types
from dataclasses import asdict, dataclass, field
from types import SimpleNamespace
from typing import Any, List, Optional


def ensure_neo4j_compat() -> None:
    try:
        __import__("neo4j")
        return
    except ImportError:
        pass

    module = types.ModuleType("neo4j")

    class Driver:
        def close(self):
            return None

    class GraphDatabase:
        @staticmethod
        def driver(*args, **kwargs):
            return Driver()

    module.Driver = Driver
    module.GraphDatabase = GraphDatabase
    sys.modules["neo4j"] = module


def ensure_neo4j_graphrag_compat() -> None:
    try:
        __import__("neo4j_graphrag")
        return
    except ImportError:
        pass

    root = types.ModuleType("neo4j_graphrag")
    experimental = types.ModuleType("neo4j_graphrag.experimental")
    components = types.ModuleType("neo4j_graphrag.experimental.components")
    schema = types.ModuleType("neo4j_graphrag.experimental.components.schema")
    kg_writer = types.ModuleType("neo4j_graphrag.experimental.components.kg_writer")
    pipeline = types.ModuleType("neo4j_graphrag.experimental.pipeline")
    kg_builder = types.ModuleType("neo4j_graphrag.experimental.pipeline.kg_builder")
    retrievers = types.ModuleType("neo4j_graphrag.retrievers")
    generation = types.ModuleType("neo4j_graphrag.generation")
    prompts = types.ModuleType("neo4j_graphrag.generation.prompts")
    indexes = types.ModuleType("neo4j_graphrag.indexes")
    embeddings = types.ModuleType("neo4j_graphrag.embeddings")
    llm = types.ModuleType("neo4j_graphrag.llm")

    @dataclass
    class PropertyType:
        name: str
        type: str
        required: bool = False

    @dataclass
    class NodeType:
        label: str
        description: str = ""
        properties: List[PropertyType] = field(default_factory=list)

    @dataclass
    class RelationshipType:
        label: str
        description: str = ""
        properties: List[PropertyType] = field(default_factory=list)

    @dataclass
    class ConstraintType:
        name: str = ""
        type: str = ""
        entity_type: str = ""
        properties: List[str] = field(default_factory=list)

    @dataclass
    class GraphSchema:
        node_types: List[Any] = field(default_factory=list)
        relationship_types: List[Any] = field(default_factory=list)
        patterns: List[Any] = field(default_factory=list)
        constraints: List[Any] = field(default_factory=list)

        @classmethod
        def from_dict(cls, data: dict) -> "GraphSchema":
            node_types = []
            for item in data.get("node_types", []):
                if isinstance(item, str):
                    node_types.append(item)
                else:
                    props = [PropertyType(**prop) for prop in item.get("properties", [])]
                    node_types.append(
                        NodeType(
                            label=item["label"],
                            description=item.get("description", ""),
                            properties=props,
                        )
                    )

            relationship_types = []
            for item in data.get("relationship_types", []):
                if isinstance(item, str):
                    relationship_types.append(item)
                else:
                    props = [PropertyType(**prop) for prop in item.get("properties", [])]
                    relationship_types.append(
                        RelationshipType(
                            label=item["label"],
                            description=item.get("description", ""),
                            properties=props,
                        )
                    )

            patterns = []
            for item in data.get("patterns", []):
                if isinstance(item, dict):
                    patterns.append((item["source"], item["relationship"], item["target"]))
                elif isinstance(item, (list, tuple)):
                    patterns.append(tuple(item))
                else:
                    patterns.append(item)
            constraints = [ConstraintType(**item) for item in data.get("constraints", [])]
            return cls(
                node_types=node_types,
                relationship_types=relationship_types,
                patterns=patterns,
                constraints=constraints,
            )

        def model_dump(self) -> dict:
            return asdict(self)

    class SchemaBuilder:
        @staticmethod
        def create_schema_model(
            node_types=None,
            relationship_types=None,
            patterns=None,
            constraints=None,
        ) -> GraphSchema:
            return GraphSchema(
                node_types=list(node_types or []),
                relationship_types=list(relationship_types or []),
                patterns=list(patterns or []),
                constraints=list(constraints or []),
            )

    class SchemaFromTextExtractor:
        def __init__(self, llm=None):
            self.llm = llm

        async def run(self, text: str) -> GraphSchema:
            return GraphSchema()

    class SchemaFromExistingGraphExtractor:
        def __init__(self, driver=None, neo4j_database: Optional[str] = None):
            self.driver = driver
            self.neo4j_database = neo4j_database

        async def run(self) -> GraphSchema:
            return GraphSchema()

    class KGWriter:
        pass

    class SimpleKGPipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run_async(self, text: str):
            return SimpleNamespace(nodes=[], relationships=[])

    class _BaseRetriever:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def search(self, **kwargs):
            return []

    class VectorRetriever(_BaseRetriever):
        pass

    class VectorCypherRetriever(_BaseRetriever):
        pass

    class Text2CypherRetriever(_BaseRetriever):
        pass

    class HybridRetriever(_BaseRetriever):
        pass

    class RagTemplate:
        def __init__(self, template: str):
            self.template = template

    class GraphRAG:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def search(self, **kwargs):
            return SimpleNamespace(answer="", retriever_result=[])

    class OpenAIEmbeddings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _BaseLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class OpenAILLM(_BaseLLM):
        pass

    class AnthropicLLM(_BaseLLM):
        pass

    class OllamaLLM(_BaseLLM):
        pass

    class VertexAILLM(_BaseLLM):
        pass

    class MistralAILLM(_BaseLLM):
        pass

    def create_vector_index(*args, **kwargs):
        return None

    def create_fulltext_index(*args, **kwargs):
        return None

    def drop_index_if_exists(*args, **kwargs):
        return None

    schema.GraphSchema = GraphSchema
    schema.NodeType = NodeType
    schema.RelationshipType = RelationshipType
    schema.PropertyType = PropertyType
    schema.ConstraintType = ConstraintType
    schema.SchemaBuilder = SchemaBuilder
    schema.SchemaFromTextExtractor = SchemaFromTextExtractor
    schema.SchemaFromExistingGraphExtractor = SchemaFromExistingGraphExtractor
    kg_writer.KGWriter = KGWriter
    kg_builder.SimpleKGPipeline = SimpleKGPipeline
    retrievers.VectorRetriever = VectorRetriever
    retrievers.VectorCypherRetriever = VectorCypherRetriever
    retrievers.Text2CypherRetriever = Text2CypherRetriever
    retrievers.HybridRetriever = HybridRetriever
    generation.GraphRAG = GraphRAG
    prompts.RagTemplate = RagTemplate
    indexes.create_vector_index = create_vector_index
    indexes.create_fulltext_index = create_fulltext_index
    indexes.drop_index_if_exists = drop_index_if_exists
    embeddings.OpenAIEmbeddings = OpenAIEmbeddings
    llm.OpenAILLM = OpenAILLM
    llm.AnthropicLLM = AnthropicLLM
    llm.OllamaLLM = OllamaLLM
    llm.VertexAILLM = VertexAILLM
    llm.MistralAILLM = MistralAILLM

    root.experimental = experimental
    root.retrievers = retrievers
    root.generation = generation
    root.indexes = indexes
    root.embeddings = embeddings
    root.llm = llm
    experimental.components = components
    experimental.pipeline = pipeline
    components.schema = schema
    components.kg_writer = kg_writer
    pipeline.kg_builder = kg_builder
    generation.prompts = prompts

    modules = {
        "neo4j_graphrag": root,
        "neo4j_graphrag.experimental": experimental,
        "neo4j_graphrag.experimental.components": components,
        "neo4j_graphrag.experimental.components.schema": schema,
        "neo4j_graphrag.experimental.components.kg_writer": kg_writer,
        "neo4j_graphrag.experimental.pipeline": pipeline,
        "neo4j_graphrag.experimental.pipeline.kg_builder": kg_builder,
        "neo4j_graphrag.retrievers": retrievers,
        "neo4j_graphrag.generation": generation,
        "neo4j_graphrag.generation.prompts": prompts,
        "neo4j_graphrag.indexes": indexes,
        "neo4j_graphrag.embeddings": embeddings,
        "neo4j_graphrag.llm": llm,
    }

    sys.modules.update(modules)


def ensure_silvaengine_dynamodb_base_compat() -> None:
    try:
        module = __import__("silvaengine_dynamodb_base")
        required = [
            "BaseModel",
            "ListObjectType",
            "delete_decorator",
            "insert_update_decorator",
            "resolve_list_decorator",
        ]
        if all(hasattr(module, name) for name in required):
            return
    except ImportError:
        module = types.ModuleType("silvaengine_dynamodb_base")

    try:
        from graphene import ObjectType
    except Exception:
        class ObjectType:
            pass

    class _BaseMeta:
        table_name = ""

    class BaseModel:
        class Meta(_BaseMeta):
            pass

        class DoesNotExist(Exception):
            pass

        def __init__(self, *args, **kwargs):
            self.attribute_values = kwargs

        @classmethod
        def get(cls, *args, **kwargs):
            raise cls.DoesNotExist()

        @classmethod
        def count(cls, *args, **kwargs):
            return 0

        @classmethod
        def query(cls, *args, **kwargs):
            return []

        @classmethod
        def scan(cls, *args, **kwargs):
            return []

        @classmethod
        def exists(cls):
            return True

        @classmethod
        def create_table(cls, *args, **kwargs):
            return None

        def save(self):
            return None

        def update(self, *args, **kwargs):
            return None

        def delete(self):
            return None

    class ListObjectType(ObjectType):
        pass

    def _identity_decorator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    module.BaseModel = getattr(module, "BaseModel", BaseModel)
    module.ListObjectType = getattr(module, "ListObjectType", ListObjectType)
    module.delete_decorator = getattr(module, "delete_decorator", _identity_decorator)
    module.insert_update_decorator = getattr(
        module, "insert_update_decorator", _identity_decorator
    )
    module.resolve_list_decorator = getattr(
        module, "resolve_list_decorator", _identity_decorator
    )
    sys.modules["silvaengine_dynamodb_base"] = module


def ensure_silvaengine_utility_compat() -> None:
    required = ["method_cache", "JSONCamelCase", "Graphql"]
    try:
        module = __import__("silvaengine_utility")
        if all(hasattr(module, name) for name in required):
            return
    except ImportError:
        module = types.ModuleType("silvaengine_utility")

    def _identity_cache(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    if not hasattr(module, "method_cache"):
        module.method_cache = _identity_cache

    if not hasattr(module, "JSONCamelCase"):
        try:
            from graphene.types.generic import GenericScalar

            module.JSONCamelCase = GenericScalar
        except Exception:
            class JSONCamelCase:
                pass

            module.JSONCamelCase = JSONCamelCase

    if not hasattr(module, "Graphql"):

        class Graphql:
            """Minimal stub for silvaengine_utility.Graphql base class."""

            def __init__(self, logger, **setting):
                self.logger = logger
                self.setting = setting

            def execute(self, schema, **params):
                from graphene import Schema

                query = params.get("query", "")
                variables = params.get("variables")
                context = params.get("context", {})
                result = schema.execute(
                    query, variables=variables, context_value=context
                )
                return {
                    "data": result.data,
                    "errors": [str(e) for e in result.errors] if result.errors else [],
                }

        module.Graphql = Graphql

    sys.modules["silvaengine_utility"] = module
