"""add vehicle catalog availability and reporting fields

Revision ID: f4816394a63f
Revises: 35688de67817
Create Date: 2026-08-17 09:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f4816394a63f'
down_revision: Union[str, Sequence[str], None] = '35688de67817'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('vehicle_type_catalog', sa.Column('model_name', sa.String(length=128), nullable=True))
    op.add_column('vehicle_type_catalog', sa.Column('gross_vehicle_weight_kg', sa.Float(), nullable=True))
    op.add_column('vehicle_type_catalog', sa.Column('cost_per_trip_reference', sa.Float(), nullable=True))
    op.add_column(
        'vehicle_type_catalog',
        sa.Column('vehicle_max_stack_weight_kg', sa.Float(), nullable=False, server_default='1000000.0'),
    )
    op.add_column('vehicle_type_catalog', sa.Column('max_speed_kmh', sa.Float(), nullable=True))
    op.add_column(
        'vehicle_type_catalog',
        sa.Column('available_from', sa.String(length=5), nullable=False, server_default='00:00'),
    )
    op.add_column(
        'vehicle_type_catalog',
        sa.Column('available_until', sa.String(length=5), nullable=False, server_default='23:59'),
    )
    op.add_column('vehicle_type_catalog', sa.Column('source_reference', sa.String(length=128), nullable=True))

def downgrade() -> None:
    op.drop_column('vehicle_type_catalog', 'source_reference')
    op.drop_column('vehicle_type_catalog', 'available_until')
    op.drop_column('vehicle_type_catalog', 'available_from')
    op.drop_column('vehicle_type_catalog', 'max_speed_kmh')
    op.drop_column('vehicle_type_catalog', 'vehicle_max_stack_weight_kg')
    op.drop_column('vehicle_type_catalog', 'cost_per_trip_reference')
    op.drop_column('vehicle_type_catalog', 'gross_vehicle_weight_kg')
    op.drop_column('vehicle_type_catalog', 'model_name')
