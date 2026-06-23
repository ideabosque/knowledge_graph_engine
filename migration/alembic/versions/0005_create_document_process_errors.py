"""create document_process_errors table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

from knowledge_graph_engine.models.postgresql.base import prefixed_table

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("document_process_errors"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("process_error_uuid", sa.String(128), nullable=False),
        sa.Column("document_source", sa.String(255), nullable=False),
        sa.Column("document_external_id", sa.String(255)),
        sa.Column("chunk_index", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("process_status", sa.String(32), default="failed"),
        sa.Column("process_count", sa.Integer, default=0),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("partition_key", "process_error_uuid"),
    )


def downgrade():
    op.drop_table(prefixed_table("document_process_errors"))