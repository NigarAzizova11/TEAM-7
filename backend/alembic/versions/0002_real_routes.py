"""real route structure: routes.source/ext_id, directions.geometry/ext_id

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("routes", sa.Column("source", sa.String(length=16), server_default=sa.text("'demo'"), nullable=False))
    op.add_column("routes", sa.Column("ext_id", sa.Integer(), nullable=True))
    op.add_column("directions", sa.Column("geometry", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("directions", sa.Column("ext_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("directions", "ext_id")
    op.drop_column("directions", "geometry")
    op.drop_column("routes", "ext_id")
    op.drop_column("routes", "source")
