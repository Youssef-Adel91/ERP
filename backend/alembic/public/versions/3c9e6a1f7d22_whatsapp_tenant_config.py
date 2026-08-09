"""whatsapp_tenant_config

Moves WhatsAppTenantConfig from tenant-schema to public.whatsapp_tenant_configs.

It was originally created as a tenant-schema table (added directly to
tenant provisioning, never given its own Alembic migration since the
tenant Alembic tree is dead code — see app.core.db.database's
_provision_tenant_schema_internal docstring). It never shipped to any
real tenant schema in this project's history, so there is no data
migration concern here — this migration simply creates the public table
outright, following the exact same pattern as 49d0941c6745 (Trust
Network) and 7a2f5e9c1b04 (Billing): a public-schema table needed for a
cross-tenant lookup that a tenant-schema table structurally cannot serve.

Here the cross-tenant lookup is: Meta's WhatsApp webhook calls ONE global
URL for the whole platform and the payload only carries phone_number_id
— app.plugins.whatsapp.api.webhooks.receive_webhook must resolve
phone_number_id -> tenant_id BEFORE it knows which tenant schema to
query, which is only possible against a public table. Hence
phone_number_id carries a UNIQUE index here — it is the reverse-lookup
key.

Revision ID: 3c9e6a1f7d22
Revises: 7a2f5e9c1b04
Create Date: 2026-08-06 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3c9e6a1f7d22'
down_revision: str | None = '7a2f5e9c1b04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'whatsapp_tenant_configs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('phone_number_id', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('access_token_ref', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('webhook_verify_token', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_whatsapp_tenant_configs_tenant_id'),
        'whatsapp_tenant_configs', ['tenant_id'], unique=True, schema='public',
    )
    op.create_index(
        op.f('ix_public_whatsapp_tenant_configs_phone_number_id'),
        'whatsapp_tenant_configs', ['phone_number_id'], unique=True, schema='public',
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_public_whatsapp_tenant_configs_phone_number_id'), table_name='whatsapp_tenant_configs', schema='public')
    op.drop_index(op.f('ix_public_whatsapp_tenant_configs_tenant_id'), table_name='whatsapp_tenant_configs', schema='public')
    op.drop_table('whatsapp_tenant_configs', schema='public')
