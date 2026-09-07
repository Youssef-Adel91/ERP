"""fix_pos_cash_shifts_timestamp_tz

Revision ID: t0o5p6q7r8s9
Revises: s9n4o5p6q7r8
Create Date: 2026-08-22 23:20:00.000000+00:00

WHY THIS EXISTS:
Live bug confirmed today: `POST /api/v1/pos/shifts/open` fails with

    asyncpg.exceptions.DataError: invalid input for query argument $12:
    datetime.datetime(2026, 8, 22, 23, 9, 56, ...
    (can't subtract offset-naive and offset-aware datetimes)
    [SQL: INSERT INTO tenant_....pos_cash_shifts (..., opened_at, closed_at)
    VALUES (..., $12::TIMESTAMP WITHOUT TIME ZONE, $13::TIMESTAMP WITHOUT
    TIME ZONE) RETURNING ...]
    [parameters: (..., datetime.datetime(..., tzinfo=datetime.timezone.utc),
    None)]

Root cause: `pos_cash_shifts.opened_at`/`closed_at` were created by
99f91dd227cd_add_missing_tenant_models.py as plain `sa.DateTime()`
(Postgres `TIMESTAMP WITHOUT TIME ZONE`) — the only two non-BaseMixin
timestamp columns on that table. Every other timestamp column on this
exact table (`created_at`, `updated_at`, `deleted_at`, all from BaseMixin,
app/core/db/base.py) was correctly created as
`sa.DateTime(timezone=True)` in that same migration. Meanwhile
`app/modules/pos/models.py::CashShift.opened_at` uses
`default_factory=lambda: datetime.now(UTC)` and
`app/modules/pos/api.py::close_shift()` sets
`shift.closed_at = datetime.now(UTC)` — both tz-aware, matching the
BaseMixin/established convention everywhere else in this codebase.
asyncpg refuses to encode a tz-aware Python datetime into a naive
`timestamp` column, so `opened_at` fails on shift open, and `closed_at`
would fail identically on shift close (same table, same bug class, fixed
together here rather than surprising the next test pass).

Fix chosen: widen the two DB columns to `TIMESTAMP WITH TIME ZONE`
(matching created_at/updated_at/deleted_at on this same table and the
`app/modules/pos/models.py` change that adds `sa_type=DateTime(timezone=
True)` to both fields) rather than stripping tzinfo in the application
code — tz-aware timestamps are the established, universal convention
here (BaseMixin, and now the app code already sends tz-aware values); no
other timestamp column anywhere in this codebase was found to be
deliberately naive.

No other columns on CashShift/pos_cash_shifts have this mismatch:
created_at/updated_at/deleted_at were already `TIMESTAMP WITH TIME ZONE`
from 99f91dd227cd; there are no other datetime-typed columns on this
table. (Aside, out of scope for this fix: `PosSale`/`pos_sales`
[app/modules/pos/models.py] has no `CREATE TABLE` in any migration under
backend/alembic/tenant/versions/ at all — a separate, pre-existing gap,
not a timestamp-tz issue, left untouched here.)

Defensive/idempotent, same `information_schema.columns` data_type check
pattern as q7l2m3n4o5p6/s9n4o5p6q7r8 (`_column_udt_name`/`_type_exists`)
so it is safe to re-run against a tenant that already has one or both
columns converted via some other path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "t0o5p6q7r8s9"
down_revision: Union[str, None] = "s9n4o5p6q7r8"
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


def _column_data_type(conn, schema: str, table: str, column: str) -> str | None:
    return conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar()


def _widen_to_timestamptz(conn, schema: str, table: str, column: str) -> None:
    data_type = _column_data_type(conn, schema, table, column)
    if data_type is None:
        # Column/table doesn't exist in this tenant schema (shouldn't
        # happen post-99f91dd227cd, but don't fail a tenant that's
        # somehow ahead/behind in an unexpected way).
        return
    if data_type == "timestamp without time zone":
        op.execute(
            f'ALTER TABLE "{schema}"."{table}" '
            f"ALTER COLUMN {column} TYPE TIMESTAMP WITH TIME ZONE "
            f"USING {column} AT TIME ZONE 'UTC'"
        )
    # else: already "timestamp with time zone" (or something else entirely
    # in a state we don't expect) — no-op either way.


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    for column in ("opened_at", "closed_at"):
        _widen_to_timestamptz(conn, schema, "pos_cash_shifts", column)


def downgrade() -> None:
    # Not reversible — same rationale as every other backfill/type-fix in
    # this chain (q7l2m3n4o5p6, r8m3n4o5p6q7, s9n4o5p6q7r8): reverting
    # would just reintroduce the live "can't subtract offset-naive and
    # offset-aware datetimes" failure on POST /api/v1/pos/shifts/open.
    pass
