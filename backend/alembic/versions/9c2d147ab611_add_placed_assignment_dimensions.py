"""persist oriented parcel assignment dimensions

Revision ID: 9c2d147ab611
Revises: 64d5c7ee792f
Create Date: 2026-08-20 14:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c2d147ab611"
down_revision: Union[str, Sequence[str], None] = "64d5c7ee792f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("parcel_assignments", sa.Column("placed_length_cm", sa.Float(), nullable=True))
    op.add_column("parcel_assignments", sa.Column("placed_width_cm", sa.Float(), nullable=True))
    op.add_column("parcel_assignments", sa.Column("placed_height_cm", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("parcel_assignments", "placed_height_cm")
    op.drop_column("parcel_assignments", "placed_width_cm")
    op.drop_column("parcel_assignments", "placed_length_cm")
