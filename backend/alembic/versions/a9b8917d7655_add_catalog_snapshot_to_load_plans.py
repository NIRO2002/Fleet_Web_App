"""add catalog_snapshot to load_plans

Revision ID: a9b8917d7655
Revises: 8f15dd8c9a6d
Create Date: 2026-08-16 09:13:28.800740
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a9b8917d7655'
down_revision: Union[str, Sequence[str], None] = '8f15dd8c9a6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('load_plans', sa.Column('catalog_snapshot', sa.JSON(), nullable=True))

def downgrade() -> None:
    op.drop_column('load_plans', 'catalog_snapshot')
