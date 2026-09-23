"""add_period_close_audit_and_monthly_periods

Revision ID: i5d6e7f8g9h0
Revises: h4c5d6e7f8g9
Create Date: 2026-09-15 00:00:00.000000+00:00

P1 Item 4 — accounting period policy decision (business control, decided by
Youssef, not by the assistant — see docs/P1_Item3_4_6_7_8_Final_Report.md
section 5 and the follow-up prompt that carried the decision):

  - Real MONTHLY accounting periods instead of the single wide-open
    2020-01-01..2099-12-31 "Open Period" row seeded by provisioning
    (app/core/db/database.py) and by the previous backfill migration
    (g3b4c5d6e7f8).
  - Only OWNER can close/reopen a period (require_role(UserRole.OWNER) —
    see app/modules/accounting/router.py).
  - Every period is created OPEN by default. No auto-close by date/schedule.
  - Existing wide-open period(s) are split into monthly periods covering the
    SAME 2020-2099 range, all OPEN — so no tenant is surprised by a closed
    historical period right after this migration runs.
  - A CLOSED period can be reopened later (not a one-way lock) — closed_by
    stays as the audit trail of who last closed it, closed_at is cleared on
    reopen.

Two idempotent, independent steps:

  1. Add `closed_by` (UUID, nullable) and `closed_at` (timestamptz, nullable)
     columns to `accounting_periods` if they do not already exist.
  2. For every tenant schema that still has one or more "wide" periods
     (duration > 5000 days — the legitimate monthly periods this migration
     creates are at most 31 days, so this threshold cannot false-positive on
     its own output), insert one row per calendar month from 2020-01 to
     2099-12 (960 months) that does not already exist (checked by exact
     start_date match — safe to run this migration N times: the Nth run
     inserts zero rows), then delete the wide row(s).

Both steps are pure per-tenant-schema data operations (no DDL is skipped
based on data, and no data operation is skipped based on DDL already being
applied), and the whole migration runs inside Alembic's own transaction, so a
failure partway rolls back both steps together — verified live by running
this migration twice in a row (see docs/P1_Item4_Final_Report.md).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i5d6e7f8g9h0"
down_revision: Union[str, None] = "h4c5d6e7f8g9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WIDE_PERIOD_THRESHOLD_DAYS = 5000  # any legitimate monthly period is <= 31 days


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
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": schema, "table": table},
        ).scalar()
    )


def _column_exists(conn, schema: str, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
            ),
            {"schema": schema, "table": table, "column": column},
        ).scalar()
    )


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, 0, 0, 0)
    if month == 12:
        end = datetime(year, 12, 31, 23, 59, 59)
    else:
        next_month_start = datetime(year, month + 1, 1, 0, 0, 0)
        end = next_month_start.replace(microsecond=0)
        # last microsecond of the month: one second before next month's start
        from datetime import timedelta
        end = next_month_start - timedelta(seconds=1)
    return start, end


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if not _table_exists(conn, schema, "accounting_periods"):
        return

    # ── 1. Add closed_by / closed_at columns (idempotent) ────────────────────
    if not _column_exists(conn, schema, "accounting_periods", "closed_by"):
        conn.execute(sa.text(f'ALTER TABLE "{schema}".accounting_periods ADD COLUMN closed_by UUID'))
    if not _column_exists(conn, schema, "accounting_periods", "closed_at"):
        conn.execute(
            sa.text(f'ALTER TABLE "{schema}".accounting_periods ADD COLUMN closed_at TIMESTAMP WITHOUT TIME ZONE')
        )

    # ── 2. Ensure every 2020-01..2099-12 monthly period exists, then drop
    #      any remaining "wide" period(s) ─────────────────────────────────
    #
    # NOTE (self-reported fix, live-run #3 uncovered this): the first
    # version of this step gated the whole fill loop on `if wide_rows:`
    # and built `existing_starts` from the *full* table including the wide
    # row(s) about to be deleted. On tenants whose wide period happened to
    # start at exactly 2020-01-01 (the normal shape seeded by
    # g3b4c5d6e7f8_backfill_open_period_and_missing_accounts), that wide
    # row's own start_date collided with the January-2020 target month, so
    # the "already exists" check skipped inserting the real January row —
    # then the wide row was deleted anyway, leaving a silent gap (verified
    # live: 9 of 14 tenants ended up with 959 periods, coverage starting
    # 2020-02-01 instead of 2020-01-01, after the first two live runs).
    #
    # Fixed by: (a) excluding the wide row ids from `existing_starts` so
    # their start_date can never falsely satisfy a target month, and
    # (b) always running the fill loop (not gated on wide_rows being
    # non-empty), so a tenant that already lost its wide row on an earlier
    # buggy run still gets its missing month(s) backfilled here — this
    # makes the migration self-healing for tenants already hit by the bug,
    # not just idempotent going forward.
    wide_rows = conn.execute(
        sa.text(
            f'SELECT id, start_date, end_date FROM "{schema}".accounting_periods '
            "WHERE (end_date - start_date) > make_interval(days => :threshold)"
        ),
        {"threshold": _WIDE_PERIOD_THRESHOLD_DAYS},
    ).fetchall()
    wide_ids = [row[0] for row in wide_rows]

    if wide_ids:
        existing_starts = {
            row[0]
            for row in conn.execute(
                sa.text(
                    f'SELECT start_date FROM "{schema}".accounting_periods '
                    "WHERE id != ALL(:wide_ids)"
                ),
                {"wide_ids": wide_ids},
            ).fetchall()
        }
    else:
        existing_starts = {
            row[0]
            for row in conn.execute(
                sa.text(f'SELECT start_date FROM "{schema}".accounting_periods')
            ).fetchall()
        }

    inserted = 0
    for year in range(2020, 2100):
        for month in range(1, 13):
            start, end = _month_bounds(year, month)
            if start in existing_starts:
                continue  # already a real monthly row from a previous run
            conn.execute(
                sa.text(
                    f'INSERT INTO "{schema}".accounting_periods '
                    "(id, created_at, updated_at, name, start_date, end_date, is_closed) "
                    "VALUES (:id, now(), now(), :name, :start_date, :end_date, false)"
                ),
                {
                    "id": uuid.uuid4(),
                    "name": f"{year:04d}-{month:02d}",
                    "start_date": start,
                    "end_date": end,
                },
            )
            inserted += 1

    # Remove any remaining wide row(s) — a no-op on any later re-run since
    # the WHERE above will find none once this has run.
    if wide_ids:
        conn.execute(
            sa.text(f'DELETE FROM "{schema}".accounting_periods WHERE id = ANY(:ids)'),
            {"ids": wide_ids},
        )


def downgrade() -> None:
    # Intentionally not reversible: collapsing 960 monthly periods back into
    # one wide period would silently reopen everything an OWNER may have
    # since closed, and dropping closed_by/closed_at would lose audit history
    # of who closed which period. Both are one-way improvements.
    pass
