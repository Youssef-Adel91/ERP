"""add_cheques_table

Revision ID: c7d8e9f0a1b2
Revises: 5bec5c78a41f
Create Date: 2026-08-09 00:00:00.000000+00:00

WHY THIS EXISTS:
app/modules/finance/models/cheques.py defines the Cheque model (table
"cheques", schema "tenant") but no migration in this chain ever created it.
It was only ever created via the legacy SQLModel.metadata.create_all()
fallback (app/core/db/database.py's `tenant_tables` list), which stopped
being the actual provisioning path once tenant provisioning switched to
pure Alembic (`TenantMigrationOrchestrator._migrate_tenant`). Every tenant
provisioned since that cutover — including via the repair script — has been
missing this table entirely, causing 500s ("relation tenant.cheques does
not exist") on every /finance/cheques/* endpoint.

The model declares cheque_type/status as proper native Postgres enums with
explicit name= and schema= (name='chequetype'/'chequestatus', schema=
'tenant'), so — unlike the VendorBill/SupplierPayment String-mismatch bug
fixed in this same session — the correct fix here is to actually create
matching native enum types, following the same CREATE TYPE + create_type=False
pattern used for `documentstate` in d4e5f6a1b2c3_phase_4a_approvals.py.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "5bec5c78a41f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Native enum types (created explicitly, matching the model's
    #      sa.Enum(..., name=..., schema="tenant") declarations) ──────────────
    # Use DO $$ to make this idempotent — if types already exist from a
    # partial previous migration run, skip creation rather than erroring.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE tenant.chequetype AS ENUM ('incoming', 'outgoing');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE tenant.chequestatus AS ENUM
                ('pending', 'deposited', 'cleared', 'bounced', 'cancelled');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # IMPORTANT: must be postgresql.ENUM (dialect-specific), NOT the generic
    # sa.Enum. Alembic's op.create_table() fires SQLAlchemy's "create type
    # before table create" event with checkfirst=False regardless of the
    # create_type flag's intent — generic sa.Enum's event handling does not
    # reliably honor create_type=False through that path (this is a known
    # Alembic/SQLAlchemy interaction, see Alembic's own docs on using ENUM
    # types), so it emitted a second, bare `CREATE TYPE` that collided with
    # the one the DO block above already created — 500ing every new tenant's
    # registration with "type \"chequetype\" already exists". Only
    # postgresql.ENUM(..., create_type=False) is honored correctly here.
    cheque_type_enum = postgresql.ENUM(
        "incoming", "outgoing",
        name="chequetype",
        schema="tenant",
        create_type=False,
    )
    cheque_status_enum = postgresql.ENUM(
        "pending", "deposited", "cleared", "bounced", "cancelled",
        name="chequestatus",
        schema="tenant",
        create_type=False,
    )

    # ── 2. cheques table (idempotent — skip if already created) ─────────────
    conn = op.get_bind()

    # Check if the table already exists in THIS tenant's schema specifically
    # (must scope by the actual current schema, not any tenant_* schema —
    # otherwise one tenant having the table would wrongly skip creating it
    # for every other tenant being migrated).
    from alembic import context as alembic_context
    current_schema = alembic_context.get_context().version_table_schema
    table_exists = conn.execute(sa.text(
        "SELECT COUNT(1) FROM information_schema.tables "
        "WHERE table_name = 'cheques' AND table_schema = :schema"
    ), {"schema": current_schema}).scalar()

    if not table_exists:
        op.create_table(
            "cheques",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cheque_number", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("issue_date", sa.Date(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=False),
            sa.Column("bank_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("cheque_type", cheque_type_enum, nullable=False),
            sa.Column("status", cheque_status_enum, nullable=False, server_default="pending"),
            sa.Column("contact_id", sa.Uuid(), nullable=False),
            sa.Column("invoice_id", sa.Uuid(), nullable=True),
            sa.Column("transaction_id", sa.Uuid(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["contact_id"], ["tenant.contacts.id"]),
            schema="tenant",
        )
        op.create_index("ix_cheques_cheque_number", "cheques", ["cheque_number"], unique=False, schema="tenant")
        op.create_index("ix_cheques_due_date", "cheques", ["due_date"], unique=False, schema="tenant")
        op.create_index("ix_cheques_status", "cheques", ["status"], unique=False, schema="tenant")
        op.create_index("ix_cheques_contact_id", "cheques", ["contact_id"], unique=False, schema="tenant")
        op.create_index(
            op.f("ix_tenant_cheques_cheque_number"), "cheques", ["cheque_number"], unique=False, schema="tenant"
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_cheques_cheque_number"), table_name="cheques", schema="tenant")
    op.drop_index("ix_cheques_contact_id", table_name="cheques", schema="tenant")
    op.drop_index("ix_cheques_status", table_name="cheques", schema="tenant")
    op.drop_index("ix_cheques_due_date", table_name="cheques", schema="tenant")
    op.drop_index("ix_cheques_cheque_number", table_name="cheques", schema="tenant")
    op.drop_table("cheques", schema="tenant")
    op.execute("DROP TYPE IF EXISTS tenant.chequestatus")
    op.execute("DROP TYPE IF EXISTS tenant.chequetype")
