"""create documents table

Revision ID: 0001
Revises:
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from knowledge_graph_engine.models.postgresql.base import Base, prefixed_table, prefixed_index

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("documents"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("document_uuid", sa.String(128), nullable=False),
        sa.Column("endpoint_id", sa.String(64)),
        sa.Column("part_id", sa.String(64)),
        sa.Column("document_source", sa.String(255), nullable=False),
        sa.Column("document_external_id", sa.String(255)),
        sa.Column("chunk_index", sa.Integer, default=0),
        sa.Column("document_title", sa.String(512)),
        sa.Column("content", sa.Text),
        sa.Column("content_embedding", postgresql.JSONB),
        sa.Column("status", sa.String(32), default="active"),
        sa.Column("updated_by", sa.String(64)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("partition_key", "document_uuid"),
    )
    op.create_index(prefixed_index("idx_documents_partition_updated_at"), prefixed_table("documents"), ["partition_key", "updated_at"])
    op.create_index(prefixed_index("idx_documents_partition_external_id"), prefixed_table("documents"), ["partition_key", "document_external_id"])
    op.create_index(prefixed_index("idx_documents_partition_status"), prefixed_table("documents"), ["partition_key", "status"])


def downgrade():
    op.drop_table(prefixed_table("documents"))