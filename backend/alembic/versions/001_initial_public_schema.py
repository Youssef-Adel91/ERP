"""
001_initial_public_schema.py — Initial Public Schema Migration

Creates the global tables in the `public` schema:
  - tenants
  - users
  - subscriptions

Revision ID: 001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tenants ───────────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("schema_name", sa.String(63), nullable=False),
        sa.Column("business_type", sa.String(100), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="EG"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="EGP"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Africa/Cairo"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending_setup"),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="public",
    )
    op.create_unique_constraint("uq_tenants_slug", "tenants", ["slug"], schema="public")
    op.create_unique_constraint("uq_tenants_schema_name", "tenants", ["schema_name"], schema="public")
    op.create_index("ix_tenants_name", "tenants", ["name"], schema="public")

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("public.tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("roles", JSONB, nullable=False, server_default='["staff"]'),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_superadmin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"], schema="public")
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"], schema="public")
    op.create_index("ix_users_email", "users", ["email"], schema="public")

    # ── subscriptions ─────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("public.tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_name", sa.String(20), nullable=False, server_default="free"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("features", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="public",
    )
    op.create_unique_constraint("uq_subscriptions_tenant_id", "subscriptions", ["tenant_id"], schema="public")


def downgrade() -> None:
    op.drop_table("subscriptions", schema="public")
    op.drop_table("users", schema="public")
    op.drop_table("tenants", schema="public")
