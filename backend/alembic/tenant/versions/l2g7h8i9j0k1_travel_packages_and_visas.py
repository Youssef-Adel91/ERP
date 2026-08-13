"""travel_packages_and_visas

Revision ID: l2g7h8i9j0k1
Revises: f4a5b6c7d8e9
Create Date: 2026-08-11 00:00:00.000000+00:00

Adds the Travel plugin's package catalog (travel_packages,
travel_itinerary_days, travel_package_components) and visa tracking
(travel_visa_applications) tables — see
app/plugins/travel/models/{package,visa}.py for the full rationale.

Idempotent (checks table existence first) — same defensive pattern used by
c7d8e9f0a1b2_add_cheques_table.py, since tenant schemas provisioned before
this migration existed need to pick it up on a plain `upgrade head` without
erroring on a partially-provisioned schema.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "l2g7h8i9j0k1"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_real_schema() -> str:
    """Return the actual schema currently in use (e.g. 'tenant_8f61ff6e_...').

    env.py installs a DDL-level text-rewriting hook that replaces 'tenant' in
    DDL statements.  But information_schema queries use SQL parameters, so they
    are NOT rewritten.  We therefore ask PostgreSQL directly which schema the
    current connection search_path points to.
    """
    bind = op.get_bind()
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar()
    if not schema or schema == "public":
        # Fallback: read from alembic x-arg passed as -x schema=<name>
        try:
            from alembic import context as _ctx
            schema = _ctx.get_x_argument(as_dictionary=True).get("schema", "tenant")
        except Exception:
            schema = "tenant"
    return schema


def _table_exists(table_name: str, schema: str | None = None) -> bool:
    bind = op.get_bind()
    real_schema = schema if schema is not None else _get_real_schema()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table_name"
            ),
            {"schema": real_schema, "table_name": table_name},
        ).scalar()
    )


def upgrade() -> None:
    if not _table_exists("travel_packages"):
        op.create_table(
            "travel_packages",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("name_ar", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("name_en", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
            sa.Column("destination", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("category", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
            sa.Column("duration_days", sa.Integer(), nullable=False),
            sa.Column("duration_nights", sa.Integer(), nullable=False),
            sa.Column("description_ar", sa.Text(), nullable=True),
            sa.Column("description_en", sa.Text(), nullable=True),
            sa.Column("base_price", sa.Numeric(18, 2), nullable=False),
            sa.Column("base_cost", sa.Numeric(18, 2), nullable=False),
            sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
            sa.Column("min_pax", sa.Integer(), nullable=False),
            sa.Column("max_pax", sa.Integer(), nullable=True),
            sa.Column("cover_image_url", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
            sa.Column("inclusions", sa.JSON(), nullable=False),
            sa.Column("exclusions", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index("ix_travel_packages_destination", "travel_packages", ["destination"], schema="tenant")
        op.create_index("ix_travel_packages_category", "travel_packages", ["category"], schema="tenant")
        op.create_index("ix_travel_packages_active", "travel_packages", ["is_active"], schema="tenant")
        op.create_index("ix_travel_packages_name_ar", "travel_packages", ["name_ar"], schema="tenant")

    if not _table_exists("travel_itinerary_days"):
        op.create_table(
            "travel_itinerary_days",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("package_id", sa.Uuid(), nullable=False),
            sa.Column("day_number", sa.Integer(), nullable=False),
            sa.Column("title_ar", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("title_en", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
            sa.Column("description_ar", sa.Text(), nullable=True),
            sa.Column("description_en", sa.Text(), nullable=True),
            sa.Column("meals_included", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["package_id"], ["tenant.travel_packages.id"], ondelete="CASCADE"),
            schema="tenant",
        )
        op.create_index("ix_travel_itinerary_days_package", "travel_itinerary_days", ["package_id"], schema="tenant")

    if not _table_exists("travel_package_components"):
        op.create_table(
            "travel_package_components",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("package_id", sa.Uuid(), nullable=False),
            sa.Column("day_number", sa.Integer(), nullable=True),
            sa.Column("component_type", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
            sa.Column("vendor_id", sa.Uuid(), nullable=True),
            sa.Column("description", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
            sa.Column("net_cost", sa.Numeric(18, 2), nullable=False),
            sa.Column("sell_price", sa.Numeric(18, 2), nullable=False),
            sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["package_id"], ["tenant.travel_packages.id"], ondelete="CASCADE"),
            # vendor_id intentionally has no FK constraint — case_vendors is created
            # by the runtime provisioning path, not a migration, so we keep it as a
            # plain UUID to avoid a missing-table error during upgrade.
            schema="tenant",
        )
        op.create_index("ix_travel_package_components_package", "travel_package_components", ["package_id"], schema="tenant")
        op.create_index("ix_travel_package_components_vendor", "travel_package_components", ["vendor_id"], schema="tenant")

    if not _table_exists("travel_visa_applications"):
        op.create_table(
            "travel_visa_applications",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("case_id", sa.Uuid(), nullable=False),
            sa.Column("passenger_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("passport_number", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
            sa.Column("destination_country", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("visa_type", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
            sa.Column("vendor_id", sa.Uuid(), nullable=True),
            sa.Column("submitted_date", sa.Date(), nullable=True),
            sa.Column("expected_decision_date", sa.Date(), nullable=True),
            sa.Column("decision_date", sa.Date(), nullable=True),
            sa.Column("visa_number", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
            sa.Column("visa_issue_date", sa.Date(), nullable=True),
            sa.Column("visa_expiry_date", sa.Date(), nullable=True),
            sa.Column("cost", sa.Numeric(18, 2), nullable=False),
            sa.Column("fee_charged", sa.Numeric(18, 2), nullable=False),
            sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            *(
                [sa.ForeignKeyConstraint(["case_id"], ["tenant.cases.id"], ondelete="CASCADE")]
                if _table_exists("cases")
                else []
            ),
            # vendor_id: same rationale as travel_package_components above
            schema="tenant",
        )
        op.create_index("ix_travel_visa_applications_case", "travel_visa_applications", ["case_id"], schema="tenant")
        op.create_index("ix_travel_visa_applications_status", "travel_visa_applications", ["status"], schema="tenant")
        op.create_index("ix_travel_visa_applications_vendor", "travel_visa_applications", ["vendor_id"], schema="tenant")


def downgrade() -> None:
    op.drop_table("travel_visa_applications", schema="tenant")
    op.drop_table("travel_package_components", schema="tenant")
    op.drop_table("travel_itinerary_days", schema="tenant")
    op.drop_table("travel_packages", schema="tenant")
