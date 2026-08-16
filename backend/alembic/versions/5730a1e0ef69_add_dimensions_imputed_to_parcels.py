"""add dimensions_imputed to parcels

Revision ID: 5730a1e0ef69
Revises: a9b8917d7655
Create Date: 2026-08-16 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '5730a1e0ef69'
down_revision: Union[str, Sequence[str], None] = 'a9b8917d7655'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        'parcels',
        sa.Column('dimensions_imputed', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

def downgrade() -> None:
    op.drop_column('parcels', 'dimensions_imputed')
