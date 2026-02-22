"""Phase C: Add geocode columns (lat, lng, geocode_status, geocoded_at, address_hash) to orders

Revision ID: phase_c_geocode_cols
Revises: add_blueprint_image_url
Create Date: 2026-02-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'phase_c_geocode_cols'
down_revision: Union[str, None] = 'add_blueprint_image_url'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('orders', sa.Column('lat', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('lng', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('geocode_status', sa.String(50), nullable=True))
    op.add_column('orders', sa.Column('geocoded_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('address_hash', sa.String(64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('orders', 'address_hash')
    op.drop_column('orders', 'geocoded_at')
    op.drop_column('orders', 'geocode_status')
    op.drop_column('orders', 'lng')
    op.drop_column('orders', 'lat')
