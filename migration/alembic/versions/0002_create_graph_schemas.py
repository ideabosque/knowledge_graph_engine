"""create graph_schemas table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from knowledge_graph_engine.models.postgresql.base import prefixed_table, prefixed_index

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("graph_schemas"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("schema_name", sa.String(255), nullable=False),
        sa.Column("endpoint_id", sa.String(64)),
        sa.Column("part_id", sa.String(64)),
        sa.Column("schema_type", sa.String(64), default="auto"),
        sa.Column("schema_definition", postgresql.JSONB),
        sa.Column("source_text_hash", sa.String(128)),
        sa.Column("neo4j_schema_string", sa.Text),
        sa.Column("text2cypher_examples", postgresql.JSONB),
        sa.Column("status", sa.String(32), default="active"),
        sa.Column("updated_by", sa.String(64)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("partition_key", "schema_name"),
    )
    op.create_index(prefixed_index("idx_graph_schemas_partition_updated_at"), prefixed_table("graph_schemas"), ["partition_key", "updated_at"])
    op.create_index(prefixed_index("idx_graph_schemas_partition_status"), prefixed_table("graph_schemas"), ["partition_key", "status"])
    # Partial unique index for single-active invariant
    op.create_index(
        prefixed_index("idx_graph_schemas_one_active"),
        prefixed_table("graph_schemas"),
        ["partition_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade():
    op.drop_table(prefixed_table("graph_schemas"))