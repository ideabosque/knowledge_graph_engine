"""create neo4j_instances table

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

from knowledge_graph_engine.models.postgresql.base import prefixed_table, prefixed_index

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        prefixed_table("neo4j_instances"),
        sa.Column("partition_key", sa.String(128), nullable=False),
        sa.Column("instance_id", sa.String(128), nullable=False),
        sa.Column("endpoint_id", sa.String(64)),
        sa.Column("part_id", sa.String(64)),
        sa.Column("neo4j_uri", sa.String(512), nullable=False),
        sa.Column("neo4j_username", sa.String(128), default="neo4j"),
        sa.Column("neo4j_password", sa.String(256), nullable=False),
        sa.Column("neo4j_database", sa.String(128), default="neo4j"),
        sa.Column("container_id", sa.String(128)),
        sa.Column("status", sa.String(32), default="active"),
        sa.Column("max_connection_pool_size", sa.Integer, default=5),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("partition_key", "instance_id"),
    )
    op.create_index(prefixed_index("idx_neo4j_instances_partition_status"), prefixed_table("neo4j_instances"), ["partition_key", "status"])
    # Partial unique index for single-active invariant
    op.create_index(
        prefixed_index("idx_neo4j_instances_one_active"),
        prefixed_table("neo4j_instances"),
        ["partition_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade():
    op.drop_table(prefixed_table("neo4j_instances"))