"""create requests table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from knowledge_graph_engine.models.postgresql.base import prefixed_table, prefixed_index

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("requests"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("request_uuid", sa.String(128), nullable=False),
        sa.Column("endpoint_id", sa.String(64)),
        sa.Column("part_id", sa.String(64)),
        sa.Column("user_query", sa.Text),
        sa.Column("cypher_query", sa.Text),
        sa.Column("search_mode", sa.String(64), default="text2cypher"),
        sa.Column("results", postgresql.JSONB),
        sa.Column("updated_by", sa.String(64)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("partition_key", "request_uuid"),
    )
    op.create_index(prefixed_index("idx_requests_partition_search_mode"), prefixed_table("requests"), ["partition_key", "search_mode"])


def downgrade():
    op.drop_table(prefixed_table("requests"))