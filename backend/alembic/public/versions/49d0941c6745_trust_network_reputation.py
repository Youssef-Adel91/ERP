"""trust_network_reputation

Drops the orphaned `global_reputation` stub table (created in dab1b0c153e8,
keyed by `contact_national_id`, never referenced by any live code — verified
via a full-repo grep before writing this migration) and recreates it to
match the real Trust Network engine schema defined in
`app.modules.trust.models.core.GlobalReputation`: a privacy-preserving,
cross-tenant reputation table keyed by an HMAC-SHA256 phone hash (never
plaintext PII), per Egyptian PDPL requirements.

Also creates `trust_contribution`, the per-tenant event ledger that feeds
the aggregate score (k-anonymity gate via `distinct_tenant_count`).

Revision ID: 49d0941c6745
Revises: ab8365cc15b1
Create Date: 2026-08-04 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '49d0941c6745'
down_revision: str | None = 'ab8365cc15b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Drop the orphaned stub ──────────────────────────────────────────────
    op.drop_index(
        op.f('ix_public_global_reputation_contact_national_id'),
        table_name='global_reputation',
        schema='public',
    )
    op.drop_table('global_reputation', schema='public')

    # ── Recreate global_reputation to match the real Trust Network engine ──
    op.create_table(
        'global_reputation',
        sa.Column('phone_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('pepper_version', sa.Integer(), nullable=False),
        sa.Column('distinct_tenant_count', sa.Integer(), nullable=False),
        sa.Column('recency_weighted_return_rate', sa.Numeric(10, 4), nullable=False),
        sa.Column(
            'band',
            sa.Enum('UNKNOWN', 'NEW', 'GOOD', 'CAUTION', 'HIGH_RISK', name='trustriskband'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('phone_hash'),
        schema='public',
    )

    # ── New: trust_contribution ledger ──────────────────────────────────────
    op.create_table(
        'trust_contribution',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('phone_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column(
            'outcome',
            sa.Enum('DELIVERED', 'RETURNED', 'REFUSED', name='shipmentoutcome'),
            nullable=False,
        ),
        sa.Column('weight', sa.Numeric(10, 4), nullable=False),
        sa.Column('is_disputed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['phone_hash'], ['public.global_reputation.phone_hash'],
        ),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_trust_contribution_phone_hash'),
        'trust_contribution', ['phone_hash'], unique=False, schema='public',
    )
    op.create_index(
        op.f('ix_public_trust_contribution_tenant_id'),
        'trust_contribution', ['tenant_id'], unique=False, schema='public',
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_public_trust_contribution_tenant_id'), table_name='trust_contribution', schema='public')
    op.drop_index(op.f('ix_public_trust_contribution_phone_hash'), table_name='trust_contribution', schema='public')
    op.drop_table('trust_contribution', schema='public')

    op.drop_table('global_reputation', schema='public')

    # Recreate the original stub shape
    op.create_table(
        'global_reputation',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('contact_national_id', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_global_reputation_contact_national_id'),
        'global_reputation', ['contact_national_id'], unique=False, schema='public',
    )
