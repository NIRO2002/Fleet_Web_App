"""add imputed dimension count to load_plans

Revision ID: 35688de67817
Revises: 5730a1e0ef69
Create Date: 2026-08-16 12:05:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '35688de67817'
down_revision: Union[str, Sequence[str], None] = '5730a1e0ef69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        'load_plans',
        sa.Column('n_parcels_with_imputed_dimensions', sa.Integer(), nullable=False, server_default='0'),
    )

def downgrade() -> None:
    op.drop_column('load_plans', 'n_parcels_with_imputed_dimensions')
