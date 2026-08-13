"""add_case_contacts_and_stage_history

Revision ID: a4c3d2e1f0b9
Revises: 99f91dd227cd
Create Date: 2026-08-11 04:35:00.000000

Adds `case_contacts` and `case_stage_history` — two Case Engine tables
(app/modules/cases/models/core.py) that were missed by the earlier
99f91dd227cd_add_missing_tenant_models migration. Their absence broke
`create_case()` for EVERY vertical built on the Case Engine (Travel,
Recruitment, Hospitality bookings, etc.) the moment a case actually tried
to record its opening stage-history row or attach a contact — not just
Travel. Discovered via a live 500 on POST /travel/packages/{id}/book:
"relation tenant_xxx.case_stage_history does not exist".

Idempotent (checks table existence first) — same defensive pattern as
l2g7h8i9j0k1_travel_packages_and_visas.py, since some tenant schemas may
have already had these tables created ad-hoc (outside Alembic) while this
migration was being written, and must not error on a second `upgrade head`.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "a4c3d2e1f0b9"
down_revision: Union[str, None] = "99f91dd227cd"
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
    if not _table_exists("case_contacts"):
        op.create_table(
            "case_contacts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("case_id", sa.Uuid(), nullable=False),
            sa.Column("contact_id", sa.Uuid(), nullable=False),
            sa.Column("role", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("meta", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["case_id"], ["tenant.cases.id"]),
            *(
                [sa.ForeignKeyConstraint(["contact_id"], ["tenant.contacts.id"])]
                if _table_exists("contacts")
                else []
            ),
            sa.UniqueConstraint("case_id", "contact_id", "role", name="uq_case_contacts_case_contact_role"),
            schema="tenant",
        )
        op.create_index("ix_tenant_case_contacts_case_id", "case_contacts", ["case_id"], schema="tenant")
        op.create_index("ix_tenant_case_contacts_contact_id", "case_contacts", ["contact_id"], schema="tenant")

    if not _table_exists("case_stage_history"):
        op.create_table(
            "case_stage_history",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("case_id", sa.Uuid(), nullable=False),
            sa.Column("from_stage", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
            sa.Column("to_stage", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("changed_by", sa.Uuid(), nullable=True),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
            sa.Column("data_snapshot", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["case_id"], ["tenant.cases.id"]),
            schema="tenant",
        )
        op.create_index("ix_case_history_case_id", "case_stage_history", ["case_id"], schema="tenant")


def downgrade() -> None:
    op.drop_table("case_stage_history", schema="tenant")
    op.drop_table("case_contacts", schema="tenant")
