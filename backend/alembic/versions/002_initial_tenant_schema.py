"""
002_initial_tenant_schema.py — Initial Tenant Schema Migration

Creates all tenant-scoped tables (to be applied to each tenant_* schema):
  - accounts       (Chart of Accounts)
  - journal_entries
  - transaction_lines (with double-entry PostgreSQL trigger)
  - contacts
  - contact_relationships
  - products
  - sale_invoices
  - sale_invoice_items

⚠️  CRITICAL: The PostgreSQL trigger `enforce_journal_balance` is created here.
    It fires AFTER INSERT/UPDATE/DELETE on transaction_lines and verifies that
    the parent journal entry remains balanced (sum(debit) == sum(credit)).
    This is the database-level enforcement of the double-entry constraint.

Revision ID: 002
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

# ── The PostgreSQL trigger function for double-entry enforcement ───────────────
_BALANCE_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION enforce_journal_balance()
RETURNS TRIGGER AS $$
DECLARE
    v_total_debit  NUMERIC(18,4);
    v_total_credit NUMERIC(18,4);
    v_entry_id     UUID;
BEGIN
    -- Determine which journal entry to check
    IF TG_OP = 'DELETE' THEN
        v_entry_id := OLD.journal_entry_id;
    ELSE
        v_entry_id := NEW.journal_entry_id;
    END IF;

    -- Only enforce balance when the entry is being posted
    -- (DRAFT entries may be temporarily unbalanced as lines are added)
    IF NOT EXISTS (
        SELECT 1 FROM journal_entries
        WHERE id = v_entry_id AND status = 'posted'
    ) THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    -- Calculate total debits and credits for this entry
    SELECT
        COALESCE(SUM(debit), 0),
        COALESCE(SUM(credit), 0)
    INTO
        v_total_debit,
        v_total_credit
    FROM transaction_lines
    WHERE journal_entry_id = v_entry_id;

    -- Enforce the fundamental double-entry constraint
    IF v_total_debit <> v_total_credit THEN
        RAISE EXCEPTION
            'DOUBLE_ENTRY_VIOLATION: Journal entry % is unbalanced. '
            'Total Debits=% Total Credits=% Difference=%',
            v_entry_id,
            v_total_debit,
            v_total_credit,
            ABS(v_total_debit - v_total_credit)
        USING ERRCODE = 'check_violation';
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
"""

_DROP_TRIGGER_FUNCTION = "DROP FUNCTION IF EXISTS enforce_journal_balance() CASCADE;"


def upgrade() -> None:
    # ── accounts ──────────────────────────────────────────────────────────────
    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=True),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_unique_constraint("uq_accounts_code", "accounts", ["code"])
    op.create_index("ix_accounts_type", "accounts", ["account_type"])
    op.create_index("ix_accounts_parent", "accounts", ["parent_id"])

    # ── journal_entries ───────────────────────────────────────────────────────
    op.create_table(
        "journal_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("source_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_journal_entries_status", "journal_entries", ["status"])
    op.create_index("ix_journal_entries_posted_at", "journal_entries", ["posted_at"])

    # ── transaction_lines (with CHECK constraint) ─────────────────────────────
    op.create_table(
        "transaction_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("journal_entry_id", UUID(as_uuid=True), sa.ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("debit", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("description", sa.String(500), nullable=True),
        sa.CheckConstraint(
            "(debit >= 0 AND credit >= 0) AND "
            "NOT (debit > 0 AND credit > 0) AND "
            "(debit > 0 OR credit > 0)",
            name="ck_transaction_lines_debit_xor_credit",
        ),
    )
    op.create_index("ix_transaction_lines_journal_entry_id", "transaction_lines", ["journal_entry_id"])
    op.create_index("ix_transaction_lines_account_id", "transaction_lines", ["account_id"])

    # ── CREATE the balance enforcement trigger function and trigger ────────────
    op.execute(_BALANCE_TRIGGER_FUNCTION)

    op.execute("""
        CREATE TRIGGER trg_enforce_journal_balance
        AFTER INSERT OR UPDATE OR DELETE ON transaction_lines
        FOR EACH ROW EXECUTE FUNCTION enforce_journal_balance();
    """)

    # ── contacts ──────────────────────────────────────────────────────────────
    op.create_table(
        "contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("contact_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_ar", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("phone_alt", sa.String(20), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("national_id", sa.String(20), nullable=True),
        sa.Column("address", JSONB, nullable=False, server_default="{}"),
        sa.Column("cod_risk_score", sa.Numeric(4, 3), nullable=False, server_default="0.000"),
        sa.Column("cod_rejection_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cod_acceptance_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "cod_risk_score >= 0.0 AND cod_risk_score <= 1.0",
            name="ck_contacts_risk_score_range",
        ),
    )
    op.create_index("ix_contacts_type", "contacts", ["contact_type"])
    op.create_index("ix_contacts_phone", "contacts", ["phone"])
    op.create_index("ix_contacts_status", "contacts", ["status"])

    # ── contact_relationships ─────────────────────────────────────────────────
    op.create_table(
        "contact_relationships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_contact_id", UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("target_contact_id", UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("relationship_type", sa.String(30), nullable=False),
        sa.Column("transaction_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_value", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("cod_rejection_rate", sa.Numeric(4, 3), nullable=False, server_default="0"),
        sa.Column("weight", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("first_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "source_contact_id", "target_contact_id", "relationship_type",
            name="uq_contact_relationships_triple",
        ),
        sa.CheckConstraint("weight >= 0.0 AND weight <= 1.0", name="ck_contact_rel_weight"),
    )
    op.create_index("ix_contact_relationships_source", "contact_relationships", ["source_contact_id"])
    op.create_index("ix_contact_relationships_target", "contact_relationships", ["target_contact_id"])

    # ── products ──────────────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_ar", sa.String(255), nullable=True),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantity_on_hand", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("reorder_level", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
        sa.CheckConstraint(
            "unit_cost >= 0 AND unit_price >= 0 AND quantity_on_hand >= 0",
            name="ck_products_non_negative",
        ),
    )

    # ── sale_invoices ─────────────────────────────────────────────────────────
    op.create_table(
        "sale_invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("invoice_number", sa.String(50), nullable=False),
        sa.Column("customer_contact_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("total_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("invoice_number", name="uq_sale_invoices_number"),
    )
    op.create_index("ix_sale_invoices_status", "sale_invoices", ["status"])
    op.create_index("ix_sale_invoices_customer", "sale_invoices", ["customer_contact_id"])

    # ── sale_invoice_items ────────────────────────────────────────────────────
    op.create_table(
        "sale_invoice_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("sale_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("total_price", sa.Numeric(18, 4), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sale_invoice_items")
    op.drop_table("sale_invoices")
    op.drop_table("products")
    op.drop_table("contact_relationships")
    op.drop_table("contacts")
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_journal_balance ON transaction_lines;")
    op.execute(_DROP_TRIGGER_FUNCTION)
    op.drop_table("transaction_lines")
    op.drop_table("journal_entries")
    op.drop_table("accounts")
