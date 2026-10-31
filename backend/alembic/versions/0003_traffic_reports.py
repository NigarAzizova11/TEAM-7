"""traffic_reports: sərnişin tıxac bildirişləri

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "traffic_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("direction_id", sa.Integer(), sa.ForeignKey("directions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("d_m", sa.Double(), nullable=False),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=16), server_default=sa.text("'user'"), nullable=False),
        sa.CheckConstraint("level IN (1, 2, 3)", name="ck_traffic_level"),
        sa.CheckConstraint("source IN ('user', 'demo_seed')", name="ck_traffic_source"),
    )
    op.create_index("ix_traffic_dir_time", "traffic_reports", ["direction_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_traffic_dir_time", table_name="traffic_reports")
    op.drop_table("traffic_reports")
