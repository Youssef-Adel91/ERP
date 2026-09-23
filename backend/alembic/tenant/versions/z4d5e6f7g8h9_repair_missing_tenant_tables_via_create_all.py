"""repair_missing_tenant_tables_via_create_all

Revision ID: z4d5e6f7g8h9
Revises: z3c4d5e6f7g8
Create Date: 2026-09-23 00:15:00.000000+00:00

WHY THIS EXISTS:
Live-reproduced: `GET /api/v1/news/` 500s for this tenant even though
`announcements` has zero FK dependencies, no enum column, and IS listed in
provision_tenant_schema's create_all `tenant_tables` (app/core/db/database.py).
No migration anywhere creates `announcements` either (confirmed by grep) --
same class of partial-provisioning gap as hr_payslips/import_dossiers
fixed earlier in this chain.

REVISION HISTORY NOTE: this revision originally tried
`SQLModel.metadata.create_all(conn, tables=[...], checkfirst=True)` as a
generic repair pass. That failed live with
`asyncpg.exceptions.DuplicateObjectError: type "auditsource" already exists`
-- SQLAlchemy's create_all(), even when given a restricted `tables=` list,
still fires metadata-level `before_create` DDL events for every Postgres
ENUM type attached anywhere on the shared SQLModel metadata (not just
those belonging to the requested tables), and checkfirst's existence
check for an already-correctly-provisioned enum elsewhere in the schema
(AuditLog.source / "auditsource", completely unrelated to this migration)
false-negatived, causing a duplicate CREATE TYPE attempt. Rewritten to
instead hand-create only the one genuinely-missing, enum-free table
directly via op.create_table(), sidestepping the shared-metadata risk
entirely. `hr_payslips` / `import_dossiers` / `import_expenses` /
`supplier_payments` are NOT touched here -- they're already handled
correctly by z1a2b3c4d5e6/z2b3c4d5e6f7/z3c4d5e6f7g8 earlier in this chain.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "z4d5e6f7g8h9"
down_revision: Union[str, None] = "z3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_schema() -> str:
    from alembic import context as alembic_context
    schema = alembic_context.get_context().version_table_schema
    if not schema:
        raise RuntimeError(
            "Schema not found in Alembic context. "
            "Pass -x schema=<name> when running tenant migrations.",
        )
    return schema


def _table_exists(conn, schema: str, table: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table"
        ),
        {"schema": schema, "table": table},
    ).scalar())


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if not _table_exists(conn, schema, "announcements"):
        op.create_table(
            "announcements",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.String(), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )


def downgrade() -> None:
    pass
