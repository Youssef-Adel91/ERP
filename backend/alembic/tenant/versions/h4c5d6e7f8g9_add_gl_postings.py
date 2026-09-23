"""add_gl_postings

Revision ID: h4c5d6e7f8g9
Revises: g3b4c5d6e7f8
Create Date: 2026-09-15 00:00:00.000000+00:00

WHY THIS EXISTS (P1 items 1 + 2, 15 Sep 2026)
----------------------------------------------
Live findings that motivated this table:

  * Duplicate posting IS prevented today — but only on the case-transition path,
    and only because `transition_case()` holds `SELECT ... FOR UPDATE` on the
    Case row. Verified live: 5 concurrent `confirmed` transitions produced
    exactly 2 journal entries (AR + AP), not 10.
  * The LEDGER ITSELF has no uniqueness at all. `JournalEntry.__table_args__`
    carries only plain indexes. Proven live by POSTing two journal entries with
    the identical reference "DUP-TEST-001" — both accepted (201, 201), two rows.
    So any path that does not hold the Case row lock (the manual journal-entry
    endpoint, an outbox/ARQ relay replay, a future publisher) can double-post.
  * Posting state was scattered across booleans in Case.data that disagree with
    reality: case 01a0a1bc-9436-777a-8252-0f682c95d265 carries BOTH
    `gl_revenue_posted: true` AND `posting_failed: true`, while the ledger holds
    ZERO entries for it.

gl_postings replaces all of that with one owned row per posting, and the
guarantee is enforced by Postgres:

    UNIQUE (source_type, source_id, entry_kind)  →  uq_gl_postings_source_kind

WHAT THIS MIGRATION DOES
-------------------------
  1. Creates the gl_posting_status enum and the gl_postings table IN THE TENANT
     SCHEMA (never public — see the enum-in-public bug this project already had).
  2. REPORTS any pre-existing duplicates instead of failing on them. Deciding
     what to do with real duplicates is a business call, not a migration's.
  3. Backfills one POSTED row per existing journal entry that identifies its
     source, deriving entry_kind from the reference prefix. Conflict-tolerant.
  4. Moves the legacy Case.data posting booleans under a single `_legacy_gl`
     key and removes them from their original names, so any code still reading
     the old name fails loudly instead of silently trusting a stale value.
     Nothing is deleted — the failure history stays readable as audit trail.

Idempotent and safe to re-run: every step is existence-guarded or
conflict-tolerant, and the whole revision runs in Alembic's transaction.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "h4c5d6e7f8g9"
down_revision: Union[str, None] = "g3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STATUS_VALUES = ("RESERVED", "POSTED", "FAILED")

# Legacy posting booleans that Case.data used to carry.
_LEGACY_KEYS = (
    "gl_revenue_posted",
    "gl_receivable_posted",
    "gl_payable_posted",
    "gl_refund_posted",
    "commission_posted",
    "deployment_fee_posted",
    "posting_failed",
    "posting_error",
    "posting_failed_stage",
)


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


def _type_exists(conn, schema: str, type_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = :schema AND t.typname = :type_name"
            ),
            {"schema": schema, "type_name": type_name},
        ).scalar()
    )


# entry_kind derived from the reference each plugin already writes.
_KIND_CASE_SQL = """
    CASE
        WHEN left(je.reference, 8) = 'JE-HOSP-' AND right(je.reference, 3)  = '-CO'          THEN 'hospitality_checkout_revenue'
        WHEN left(je.reference, 8) = 'JE-HOSP-' AND right(je.reference, 5)  = '-CANC'        THEN 'hospitality_cancellation_penalty'
        WHEN left(je.reference, 8) = 'JE-RENT-' AND right(je.reference, 4)  = '-RET'         THEN 'rental_return_revenue'
        WHEN left(je.reference, 7) = 'JE-TRV-'  AND right(je.reference, 3)  = '-AR'          THEN 'travel_customer_receivable'
        WHEN left(je.reference, 7) = 'JE-TRV-'  AND right(je.reference, 3)  = '-AP'          THEN 'travel_supplier_payable'
        WHEN left(je.reference, 7) = 'JE-TRV-'  AND right(je.reference, 7)  = '-REFUND'      THEN 'travel_cancellation_refund'
        WHEN left(je.reference, 7) = 'JE-TRV-'  AND right(je.reference, 8)  = '-PENALTY'     THEN 'travel_cancellation_penalty'
        WHEN left(je.reference, 7) = 'JE-REC-'  AND right(je.reference, 11) = '-CONTRACTED'  THEN 'recruitment_commission'
        WHEN left(je.reference, 7) = 'JE-REC-'  AND right(je.reference, 9)  = '-DEPLOYED'    THEN 'recruitment_deployment_fee'
        ELSE 'legacy_unclassified'
    END
"""

def _report_existing_duplicates(conn, schema: str) -> None:
    """Print duplicate groups. Never raises — the decision is the owner's.

    Two kinds are reported:
      A. journal entries sharing a `reference` (catches hand-made duplicates
         such as the DUP-TEST-001 pair created deliberately during P1 testing);
      B. journal entries that would map to the SAME gl_postings key, i.e. the
         rows the backfill below cannot represent as separate postings.
    """
    if not _table_exists(conn, schema, "journal_entries"):
        return

    dup_refs = conn.execute(
        sa.text(
            f'SELECT reference, COUNT(*) AS n '
            f'FROM "{schema}".journal_entries '
            "WHERE reference IS NOT NULL "
            "GROUP BY reference HAVING COUNT(*) > 1 ORDER BY n DESC"
        )
    ).fetchall()

    dup_keys = conn.execute(
        sa.text(
            f"SELECT je.source_type, je.source_id, {_KIND_CASE_SQL} AS entry_kind, "
            f'COUNT(*) AS n FROM "{schema}".journal_entries je '
            "WHERE je.source_id IS NOT NULL "
            f"GROUP BY je.source_type, je.source_id, {_KIND_CASE_SQL} "
            "HAVING COUNT(*) > 1 ORDER BY n DESC"
        )
    ).fetchall()

    if not dup_refs and not dup_keys:
        print(f"[gl_postings] {schema}: no pre-existing duplicate journal entries found.")
        return

    print("")
    print("=" * 78)
    print(f"[gl_postings] DUPLICATE JOURNAL ENTRIES DETECTED in schema {schema}")
    print("  Nothing is deleted or merged by this migration — reporting only.")
    print("  Decide how to handle these before relying on the ledger.")
    if dup_refs:
        print("  -- same `reference` --")
        for row in dup_refs:
            print(f"     reference={row[0]!r}  count={row[1]}")
    if dup_keys:
        print("  -- would collide on UNIQUE(source_type, source_id, entry_kind) --")
        for row in dup_keys:
            print(f"     source={row[0]}/{row[1]}  entry_kind={row[2]}  count={row[3]}")
        print("  Only the FIRST of each group gets a gl_postings row (ON CONFLICT")
        print("  DO NOTHING); the others remain in the ledger, unguarded.")
    print("=" * 78)
    print("")


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. Enum + table, inside the tenant schema ────────────────────────────
    if not _type_exists(conn, schema, "gl_posting_status"):
        values_sql = ", ".join(f"'{v}'" for v in _STATUS_VALUES)
        op.execute(
            f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."gl_posting_status" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )

    if not _table_exists(conn, schema, "gl_postings"):
        op.create_table(
            "gl_postings",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_type", sa.String(length=50), nullable=False),
            sa.Column("source_id", sa.Uuid(), nullable=False),
            sa.Column("entry_kind", sa.String(length=100), nullable=False),
            sa.Column(
                "status",
                postgresql.ENUM(
                    *_STATUS_VALUES, name="gl_posting_status",
                    schema=schema, create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
            sa.Column("invoice_number", sa.String(length=100), nullable=True),
            sa.Column("amount", sa.Numeric(18, 4), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="EGP"),
            sa.Column("error_type", sa.String(length=100), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "last_attempt_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            # THE guarantee this whole table exists for.
            sa.UniqueConstraint(
                "source_type", "source_id", "entry_kind",
                name="uq_gl_postings_source_kind",
            ),
            schema=schema,
        )
        op.create_index(
            "ix_gl_postings_source", "gl_postings",
            ["source_type", "source_id"], schema=schema,
        )
        op.create_index("ix_gl_postings_status", "gl_postings", ["status"], schema=schema)
        op.create_index("ix_gl_postings_source_id", "gl_postings", ["source_id"], schema=schema)
        op.create_index(
            "ix_gl_postings_journal_entry_id", "gl_postings",
            ["journal_entry_id"], schema=schema,
        )

    # ── 2. Report duplicates BEFORE backfilling (never fail on them) ─────────
    _report_existing_duplicates(conn, schema)

    # ── 3. Backfill from journal entries that identify their source ─────────
    # JournalEntry.source_type is the literal 'invoice' written by
    # handle_invoice_created, but source_id is the CASE id (each plugin sets
    # invoice_id = str(case.id)), so the posting's source_type is 'case'.
    if _table_exists(conn, schema, "journal_entries") and _table_exists(conn, schema, "gl_postings"):
        before = conn.execute(
            sa.text(f'SELECT COUNT(*) FROM "{schema}".gl_postings')
        ).scalar()
        conn.execute(
            sa.text(
                f'INSERT INTO "{schema}".gl_postings '
                "(id, created_at, updated_at, source_type, source_id, entry_kind, "
                " status, journal_entry_id, invoice_number, amount, currency, "
                " attempts, last_attempt_at) "
                "SELECT gen_random_uuid(), now(), now(), 'case', je.source_id, "
                f"       {_KIND_CASE_SQL}, "
                f'       CAST(\'POSTED\' AS "{schema}".gl_posting_status), je.id, '
                "       replace(je.reference, 'JE-', ''), "
                f'       (SELECT COALESCE(SUM(l.debit), 0) FROM "{schema}".journal_entry_lines l '
                "         WHERE l.journal_entry_id = je.id), "
                "       'EGP', 1, je.created_at "
                f'FROM "{schema}".journal_entries je '
                "WHERE je.source_id IS NOT NULL "
                "ON CONFLICT ON CONSTRAINT uq_gl_postings_source_kind DO NOTHING"
            )
        )
        after = conn.execute(
            sa.text(f'SELECT COUNT(*) FROM "{schema}".gl_postings')
        ).scalar()
        candidates = conn.execute(
            sa.text(
                f'SELECT COUNT(*) FROM "{schema}".journal_entries WHERE source_id IS NOT NULL'
            )
        ).scalar()
        print(
            f"[gl_postings] {schema}: backfilled {after - before} posting row(s) "
            f"from {candidates} source-identified journal entr(y/ies); "
            f"{candidates - (after - before)} skipped as duplicates of an existing key."
        )

    # ── 4. Retire the legacy Case.data booleans ─────────────────────────────
    # Moved under `_legacy_gl` and removed from their original names so that any
    # code still reading e.g. case.data["gl_revenue_posted"] now gets None and
    # fails visibly, instead of quietly trusting a value that may contradict the
    # ledger. Case.data is a `json` column (not jsonb), hence the casts.
    if _table_exists(conn, schema, "cases"):
        keys_sql = ", ".join(f"'{k}'" for k in _LEGACY_KEYS)
        moved = conn.execute(
            sa.text(
                f'UPDATE "{schema}".cases c SET data = ( '
                f"    (c.data::jsonb - ARRAY[{keys_sql}]) "
                "     || jsonb_build_object('_legacy_gl', COALESCE(( "
                "            SELECT jsonb_object_agg(e.key, e.value) "
                "            FROM jsonb_each(c.data::jsonb) AS e "
                f"            WHERE e.key = ANY(ARRAY[{keys_sql}]) "
                "        ), '{}'::jsonb)) "
                ")::json "
                f"WHERE jsonb_exists_any(c.data::jsonb, ARRAY[{keys_sql}])"
            )
        ).rowcount
        print(f"[gl_postings] {schema}: moved legacy posting flags on {moved} case(s) under '_legacy_gl'.")


def downgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # Restore the legacy flags to their original names before dropping the table,
    # so a rollback leaves the old code path working.
    if _table_exists(conn, schema, "cases"):
        conn.execute(
            sa.text(
                f'UPDATE "{schema}".cases c SET data = ( '
                "    (c.data::jsonb - '_legacy_gl') || COALESCE(c.data::jsonb->'_legacy_gl', '{}'::jsonb) "
                ")::json "
                "WHERE jsonb_exists(c.data::jsonb, '_legacy_gl')"
            )
        )

    if _table_exists(conn, schema, "gl_postings"):
        op.drop_table("gl_postings", schema=schema)
    if _type_exists(conn, schema, "gl_posting_status"):
        op.execute(f'DROP TYPE "tenant"."gl_posting_status"')
