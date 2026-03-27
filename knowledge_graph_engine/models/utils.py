# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "silvaengine"

import logging

from .neo4j_instance import Neo4jInstanceModel
from .document import DocumentModel
from .graph_schema import GraphSchemaModel
from .request import RequestModel
from .document_process_error import DocumentProcessErrorModel


def initialize_tables(logger: logging.Logger) -> None:
    """Create DynamoDB tables if they don't exist. Same pattern as aace."""
    models = [
        Neo4jInstanceModel,
        DocumentModel,
        GraphSchemaModel,
        RequestModel,
        DocumentProcessErrorModel,
    ]
    for model in models:
        if not model.exists():
            model.create_table(
                read_capacity_units=1,
                write_capacity_units=1,
                wait=True,
            )
            logger.info(f"Created table: {model.Meta.table_name}")