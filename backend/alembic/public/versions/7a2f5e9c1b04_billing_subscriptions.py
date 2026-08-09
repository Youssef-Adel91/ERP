"""billing_subscriptions

Creates the Billing & Subscriptions domain (Phase 8, launch-blocking):
public.billing_plan, public.billing_subscription,
public.billing_subscription_invoice, public.billing_payment_attempt —
matching app.modules.billing.models.core exactly. All four are public-schema
(cross-tenant) tables, following the same pattern as the Trust Network
tables added in 49d0941c6745.

Revision ID: 7a2f5e9c1b04
Revises: 49d0941c6745
Create Date: 2026-08-04 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7a2f5e9c1b04'
down_revision: str | None = '49d0941c6745'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── billing_plan ─────────────────────────────────────────────────────────
    op.create_table(
        'billing_plan',
        sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column(
            'tier',
            sa.Enum('ENTRY', 'PROFESSIONAL', 'ENTERPRISE', name='plantier'),
            nullable=False,
        ),
        sa.Column('price_monthly', sa.Numeric(10, 2), nullable=False),
        sa.Column('entitlements', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('code'),
        schema='public',
    )

    # ── billing_subscription ────────────────────────────────────────────────
    op.create_table(
        'billing_subscription',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('plan_code', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column(
            'state',
            sa.Enum('TRIALING', 'ACTIVE', 'PAST_DUE', 'SUSPENDED', 'CANCELLED', name='subscriptionstate'),
            nullable=False,
        ),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['plan_code'], ['public.billing_plan.code']),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_billing_subscription_tenant_id'),
        'billing_subscription', ['tenant_id'], unique=True, schema='public',
    )
    op.create_index(
        op.f('ix_public_billing_subscription_plan_code'),
        'billing_subscription', ['plan_code'], unique=False, schema='public',
    )

    # ── billing_subscription_invoice ────────────────────────────────────────
    op.create_table(
        'billing_subscription_invoice',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('subscription_id', sa.Uuid(), nullable=False),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column(
            'status',
            sa.Enum('DRAFT', 'OPEN', 'PAID', 'VOID', 'UNCOLLECTIBLE', name='invoicestatus'),
            nullable=False,
        ),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['public.billing_subscription.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_billing_subscription_invoice_subscription_id'),
        'billing_subscription_invoice', ['subscription_id'], unique=False, schema='public',
    )

    # ── billing_payment_attempt ─────────────────────────────────────────────
    op.create_table(
        'billing_payment_attempt',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('invoice_id', sa.Uuid(), nullable=False),
        sa.Column('provider', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('transaction_ref', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'SUCCEEDED', 'FAILED', name='paymentstatus'),
            nullable=False,
        ),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['public.billing_subscription_invoice.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_billing_payment_attempt_invoice_id'),
        'billing_payment_attempt', ['invoice_id'], unique=False, schema='public',
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_public_billing_payment_attempt_invoice_id'), table_name='billing_payment_attempt', schema='public')
    op.drop_table('billing_payment_attempt', schema='public')

    op.drop_index(op.f('ix_public_billing_subscription_invoice_subscription_id'), table_name='billing_subscription_invoice', schema='public')
    op.drop_table('billing_subscription_invoice', schema='public')

    op.drop_index(op.f('ix_public_billing_subscription_plan_code'), table_name='billing_subscription', schema='public')
    op.drop_index(op.f('ix_public_billing_subscription_tenant_id'), table_name='billing_subscription', schema='public')
    op.drop_table('billing_subscription', schema='public')

    op.drop_table('billing_plan', schema='public')

    sa.Enum(name='paymentstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='invoicestatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='subscriptionstate').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='plantier').drop(op.get_bind(), checkfirst=True)
