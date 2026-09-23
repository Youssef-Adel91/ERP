"""add_employer_contact_type

Revision ID: n5o6p7q8r9s0
Revises: i5d6e7f8g9h0
Create Date: 2026-09-20 00:00:00.000000+00:00

WHY THIS EXISTS:
Live-reproduced (four_verticals_scenario_report.md, §3.2): the recruitment
plugin's "طلب توظيف جديد" (new job order) form requires a sponsor/employer
contact (JobOrder.sponsor_id -> tenant.contacts.id, see
app/plugins/recruitment/api.py + models/job_orders.py). Nothing on the
backend actually restricts what ContactType a sponsor must have — the FK
just points at any row in tenant.contacts — but the Contacts UI (and the
Python-side ContactType enum backing the DB column) only ever offered
"customer" / "supplier", with no "employer" option. In practice a user
onboarding a foreign employer/sponsor had nowhere honest to put them:
mislabeling them as a "customer" or "supplier" is the only workaround,
which is exactly what the report flagged as the blocker.

Fix: add a third ContactType member, "employer", matching
app.modules.contacts.models.ContactType.EMPLOYER (see that file for the
Python-side change). The `contacttype` enum is a real Postgres enum
(tenant.contacttype), created via SQLAlchemy's own checkfirst logic — not a
`create_type=False`-gated one like employeestatus/leaverequeststatus/etc
elsewhere in this chain — but existing tenants' schemas already have this
type created with only ('customer', 'supplier'), so adding a member here
requires an explicit ALTER TYPE ... ADD VALUE, same as any other tenant
already past the point where a new tenant's fresh CREATE TYPE would have
picked up the third value for free.

ALTER TYPE ... ADD VALUE is safe to run inside a transaction on Postgre
12+ (the value just can't be *used* in the same transaction that adds it,
which this migration doesn't need to do) — no special non-transactional
handling required, unlike older Postgres versions.

Idempotent via the same pattern used throughout this chain (checks
pg_enum for the label before adding it) — safe to re-run.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, None] = "i5d6e7f8g9h0"
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


def _enum_value_exists(conn, schema: str, type_name: str, value: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = :schema AND t.typname = :type_name AND e.enumlabel = :value"
        ),
        {"schema": schema, "type_name": type_name, "value": value},
    ).scalar())


def _type_exists(conn, schema: str, type_name: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = :schema AND t.typname = :type_name"
        ),
        {"schema": schema, "type_name": type_name},
    ).scalar())


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if not _type_exists(conn, schema, "contacttype"):
        # A brand-new tenant that hasn't created contacts yet — the type
        # will be created fresh (with all three values, since the model
        # now declares EMPLOYER too) the first time SQLAlchemy's checkfirst
        # enum-creation logic runs against tenant.contacts. Nothing to do.
        return

    if not _enum_value_exists(conn, schema, "contacttype", "employer"):
        op.execute(f'ALTER TYPE "{schema}"."contacttype" ADD VALUE \'employer\'')


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — removing an enum member
    # requires rebuilding the type from scratch, which would fail outright
    # if any contact row already uses 'employer'. Not reversible, same
    # rationale as w3r8s9t0u1v2/q7l2m3n4o5p6 elsewhere in this chain.
    pass
