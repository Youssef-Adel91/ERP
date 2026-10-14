"""add_travel_passengers_visa_docs_soft_delete

Revision ID: A1b2c3d4e5f6
Revises: z6c1a2r3r4i5
Create Date: 2026-09-09 00:00:00.000000+00:00

Three idempotent changes to support Travel plugin commercial readiness:

1. travel_passengers — new table for structured per-passenger CRUD
   (works alongside the existing JSONB passenger_manifest in Case.data)

2. travel_visa_documents — new table for visa document attachments
   stored as BYTEA (passport scans, photos, forms — max 5 MB enforced at API layer)

3. travel_visa_applications.is_active — new column for soft delete
   (replaces hard DELETE on records that have financial impact:
    fee_charged > 0 or cost > 0)

All three are idempotent: checks table/column existence before DDL,
same defensive pattern used by l2g7h8i9j0k1_travel_packages_and_visas.py.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "A1b2c3d4e5f6"
down_revision: Union[str, None] = "z6c1a2r3r4i5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_real_schema() -> str:
    bind = op.get_bind()
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar()
    if not schema or schema == "public":
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


def _column_exists(table_name: str, column_name: str, schema: str | None = None) -> bool:
    bind = op.get_bind()
    real_schema = schema if schema is not None else _get_real_schema()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table AND column_name = :col"
            ),
            {"schema": real_schema, "table": table_name, "col": column_name},
        ).scalar()
    )


def upgrade() -> None:
    real_schema = _get_real_schema()

    # ── 1. travel_passengers ────────────────────────────────────────────────────
    if not _table_exists("travel_passengers"):
        op.create_table(
            "travel_passengers",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("case_id", sa.Uuid(), nullable=False),
            sa.Column("visa_application_id", sa.Uuid(), nullable=True),
            sa.Column("full_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("full_name_ar", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
            sa.Column("passport_number", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
            sa.Column("passport_expiry", sa.Date(), nullable=True),
            sa.Column("date_of_birth", sa.Date(), nullable=True),
            sa.Column("nationality", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
            sa.Column("gender", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
            sa.Column("passenger_type", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False, server_default="adult"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.ForeignKeyConstraint(
                ["case_id"], [f"{real_schema}.cases.id"],
                name=f"fk_travel_passengers_case_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["visa_application_id"], [f"{real_schema}.travel_visa_applications.id"],
                name=f"fk_travel_passengers_visa_id",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=real_schema,
        )
        op.create_index("ix_travel_passengers_case", "travel_passengers", ["case_id"], schema=real_schema)
        op.create_index("ix_travel_passengers_visa", "travel_passengers", ["visa_application_id"], schema=real_schema)

    # ── 2. travel_visa_documents ─────────────────────────────────────────────────
    if not _table_exists("travel_visa_documents"):
        op.create_table(
            "travel_visa_documents",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("visa_id", sa.Uuid(), nullable=False),
            sa.Column("filename", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("content_type", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("data", sa.LargeBinary(), nullable=False),
            sa.Column("uploaded_by", sa.Uuid(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["visa_id"], [f"{real_schema}.travel_visa_applications.id"],
                name=f"fk_travel_visa_documents_visa_id",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=real_schema,
        )
        op.create_index("ix_travel_visa_documents_visa", "travel_visa_documents", ["visa_id"], schema=real_schema)

    # ── 3. travel_visa_applications.is_active ────────────────────────────────────
    if not _column_exists("travel_visa_applications", "is_active"):
        op.add_column(
            "travel_visa_applications",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            schema=real_schema,
        )
        # Backfill: mark all existing records active (server_default handles new rows)
        op.execute(
            sa.text(f'UPDATE "{real_schema}"."travel_visa_applications" SET is_active = TRUE WHERE is_active IS NULL')
        )


def downgrade() -> None:
    real_schema = _get_real_schema()

    # Remove is_active column from visa applications
    if _column_exists("travel_visa_applications", "is_active"):
        op.drop_column("travel_visa_applications", "is_active", schema=real_schema)

    # Drop visa documents table
    if _table_exists("travel_visa_documents"):
        op.drop_index("ix_travel_visa_documents_visa", "travel_visa_documents", schema=real_schema)
        op.drop_table("travel_visa_documents", schema=real_schema)

    # Drop passengers table
    if _table_exists("travel_passengers"):
        op.drop_index("ix_travel_passengers_visa", "travel_passengers", schema=real_schema)
        op.drop_index("ix_travel_passengers_case", "travel_passengers", schema=real_schema)
        op.drop_table("travel_passengers", schema=real_schema)
