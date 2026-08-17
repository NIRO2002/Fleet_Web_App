"""add parcel and plan status, carryover, and run manifest fields

Revision ID: 64d5c7ee792f
Revises: f4816394a63f
Create Date: 2026-08-17 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '64d5c7ee792f'
down_revision: Union[str, Sequence[str], None] = 'f4816394a63f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        'parcels',
        sa.Column('status', sa.String(length=16), nullable=False, server_default='PENDING'),
    )
    op.create_index('ix_parcels_status', 'parcels', ['status'])
    op.add_column('parcels', sa.Column('plan_id', sa.String(length=64), nullable=True))
    op.create_index('ix_parcels_plan_id', 'parcels', ['plan_id'])
    op.add_column('parcels', sa.Column('carried_over_from_date', sa.Date(), nullable=True))

    op.add_column(
        'load_plans',
        sa.Column('n_carryover_parcels', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'load_plans',
        sa.Column('status', sa.String(length=16), nullable=False, server_default='DRAFT'),
    )
    op.add_column('load_plans', sa.Column('run_manifest', sa.JSON(), nullable=True))

def downgrade() -> None:
    op.drop_column('load_plans', 'run_manifest')
    op.drop_column('load_plans', 'status')
    op.drop_column('load_plans', 'n_carryover_parcels')

    op.drop_column('parcels', 'carried_over_from_date')
    op.drop_index('ix_parcels_plan_id', table_name='parcels')
    op.drop_column('parcels', 'plan_id')
    op.drop_index('ix_parcels_status', table_name='parcels')
    op.drop_column('parcels', 'status')
