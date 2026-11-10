"""
app/modules/accounting/router.py — Accounting Module API Routes

All endpoints require a valid Bearer token. The `get_tenant_db` dependency
sets `search_path = tenant_{id}` so all queries hit the correct schema.
"""

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_tenant_db
from app.core.security.security import require_role
from app.modules.accounting import service
from app.modules.accounting.models import AccountType, JournalEntryStatus
from app.modules.accounting.reports import generate_trial_balance
from app.modules.accounting.schemas import (
    AccountBalanceResponse,
    AccountCreateRequest,
    AccountResponse,
    AccountingPeriodResponse,
    JournalEntryCreateRequest,
    JournalEntryResponse,
    TrialBalanceRow,
)
from app.modules.accounting.services.journal import ClosedPeriodError
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import UserRole

logger = logging.getLogger(__name__)
router = APIRouter()

# All accounting data (Chart of Accounts, account balances, journal entries)
# is sensitive financial information. Restrict every endpoint in this router
# to roles that legitimately need it — previously any authenticated user of
# any role (e.g. SALES, STAFF) could read/write the general ledger.
_FINANCE_ROLES = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTING))

# P1 Item 4 (business-control decision, not made unilaterally — see
# docs/P1_Item3_4_6_7_8_Final_Report.md section 5 and the follow-up prompt
# that carried Youssef's decision): only OWNER may close or reopen an
# accounting period. Not ADMIN, not ACCOUNTING — deliberately narrower than
# _FINANCE_ROLES above, which read/write day-to-day ledger data but must not
# be able to lock or unlock an entire period.
_OWNER_ONLY = Depends(require_role(UserRole.OWNER))


# ══════════════════════════════════════════════════════════════════
# CHART OF ACCOUNTS
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/accounts",
    response_model=list[AccountResponse],
    summary="List Chart of Accounts",
    tags=["Accounting - Accounts"],
    dependencies=[_FINANCE_ROLES],
)
async def list_accounts(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    account_type: AccountType | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AccountResponse]:
    """
    Returns all accounts in the tenant's Chart of Accounts.

    The default Chart (seeded on registration) includes:
      1100 Cash, 1200 AR, 2100 AP, 4010 Revenue, 5010 COGS…
    """
    accounts = await service.get_accounts(db, account_type=account_type, limit=limit, offset=offset)
    return [AccountResponse.model_validate(a) for a in accounts]


@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new account to Chart of Accounts",
    tags=["Accounting - Accounts"],
    dependencies=[_FINANCE_ROLES],
)
async def create_account(
    data: AccountCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> AccountResponse:
    try:
        account = await service.create_account(data, db)
        return AccountResponse.model_validate(account)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/accounts/{account_code}/balance",
    response_model=AccountBalanceResponse,
    summary="Get running balance for an account (POSTED entries only)",
    tags=["Accounting - Accounts"],
    dependencies=[_FINANCE_ROLES],
)
async def get_account_balance(
    account_code: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> AccountBalanceResponse:
    """
    Returns total debits, total credits, and net balance from all **POSTED**
    journal entries for this account.

    DRAFT entries are excluded — they have not been approved yet.
    """
    try:
        return await service.get_account_balance(account_code, db)
    except service.AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ══════════════════════════════════════════════════════════════════
# JOURNAL ENTRIES
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/journal-entries",
    response_model=list[JournalEntryResponse],
    summary="List journal entries",
    description=(
        "Lists all journal entries in the tenant's schema.\n\n"
        "Filter by `status=draft` to see unposted entries, "
        "`status=posted` to see the immutable accounting record.\n\n"
        "**Note:** Entries created automatically by the `invoice.created` event "
        "will appear here with `source_type='invoice'`."
    ),
    tags=["Accounting - Journal Entries"],
    dependencies=[_FINANCE_ROLES],
)
async def list_journal_entries(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    entry_status: JournalEntryStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[JournalEntryResponse]:
    entries = await service.get_journal_entries(
        db, status_filter=entry_status, limit=limit, offset=offset,
    )
    return [JournalEntryResponse.model_validate(e) for e in entries]


@router.post(
    "/journal-entries",
    response_model=JournalEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual DRAFT journal entry",
    description=(
        "Manually create a balanced journal entry.\n\n"
        "**Validation (3 layers):**\n"
        "1. Pydantic: debit XOR credit per line, Σdebits == Σcredits\n"
        "2. Service: second balance check before any DB write\n"
        "3. DB: `CHECK (debit XOR credit)` constraint on each line row\n\n"
        "The entry is created as `DRAFT`. Call `POST ./{id}/post` to finalize it."
    ),
    tags=["Accounting - Journal Entries"],
    dependencies=[_FINANCE_ROLES],
)
async def create_journal_entry(
    data: JournalEntryCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> JournalEntryResponse:
    try:
        entry = await service.create_draft_journal_entry(data, current_user.id, db)
        return JournalEntryResponse.model_validate(entry)
    except service.UnbalancedEntryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "UNBALANCED_ENTRY", "message": str(exc)},
        ) from exc


@router.post(
    "/journal-entries/{entry_id}/post",
    response_model=JournalEntryResponse,
    summary="Post a DRAFT journal entry (makes it immutable)",
    description=(
        "Transitions a `DRAFT` journal entry to `POSTED`.\n\n"
        "A POSTED entry is **immutable** — it cannot be edited or deleted.\n"
        "To correct a posted entry, use `POST ./{id}/reverse` instead."
    ),
    tags=["Accounting - Journal Entries"],
    dependencies=[_FINANCE_ROLES],
)
async def post_journal_entry(
    entry_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> JournalEntryResponse:
    try:
        entry = await service.post_journal_entry(entry_id, current_user.id, db)
        return JournalEntryResponse.model_validate(entry)
    except ClosedPeriodError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "CLOSED_PERIOD", "message": str(exc)},
        ) from exc
    except service.PostedEntryMutationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/journal-entries/{entry_id}/reverse",
    response_model=JournalEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a reversing entry (swaps all debits and credits)",
    description=(
        "Creates a new `DRAFT` journal entry that is the mirror image of the "
        "original POSTED entry (all debits become credits and vice versa).\n\n"
        "Use this to correct accounting errors without modifying posted history."
    ),
    tags=["Accounting - Journal Entries"],
    dependencies=[_FINANCE_ROLES],
)
async def create_reversing_entry(
    entry_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> JournalEntryResponse:
    try:
        reversing = await service.create_reversing_entry(entry_id, current_user.id, db)
        return JournalEntryResponse.model_validate(reversing)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# ══════════════════════════════════════════════════════════════════
# ACCOUNTING PERIODS (P1 Item 4)
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/periods",
    response_model=list[AccountingPeriodResponse],
    summary="List accounting periods",
    tags=["Accounting - Periods"],
    dependencies=[_FINANCE_ROLES],
)
async def list_periods(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    limit: int = Query(default=500, le=1200),
    offset: int = Query(default=0, ge=0),
) -> list[AccountingPeriodResponse]:
    periods = await service.list_periods(db, limit=limit, offset=offset)
    return [AccountingPeriodResponse.model_validate(p) for p in periods]


@router.post(
    "/periods/{period_id}/close",
    response_model=AccountingPeriodResponse,
    summary="Close an accounting period (OWNER only)",
    description=(
        "Blocks any further journal-entry posting dated inside this period "
        "(both the automated invoice.created path and manual DRAFT->POST). "
        "Reversible — see POST ./{period_id}/reopen. Restricted to OWNER, "
        "not ADMIN or ACCOUNTING (business-control decision, P1 Item 4)."
    ),
    tags=["Accounting - Periods"],
    dependencies=[_OWNER_ONLY],
)
async def close_period(
    period_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> AccountingPeriodResponse:
    try:
        period = await service.close_period(period_id, current_user.id, db)
        return AccountingPeriodResponse.model_validate(period)
    except service.PeriodNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.PeriodAlreadyClosedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/periods/{period_id}/reopen",
    response_model=AccountingPeriodResponse,
    summary="Reopen a CLOSED accounting period (OWNER only)",
    description=(
        "Allows posting into this period again. Not a routine action — "
        "meant for a deliberate, approved correction (P1 Item 4 decision)."
    ),
    tags=["Accounting - Periods"],
    dependencies=[_OWNER_ONLY],
)
async def reopen_period(
    period_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> AccountingPeriodResponse:
    try:
        period = await service.reopen_period(period_id, db)
        return AccountingPeriodResponse.model_validate(period)
    except service.PeriodNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.PeriodAlreadyOpenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


# ══════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/reports/trial-balance",
    response_model=list[TrialBalanceRow],
    summary="Trial Balance report — verifies Σdebits == Σcredits across the GL",
    description=(
        "Aggregates every **POSTED** journal entry line by GL account, computes "
        "each account's net balance by its normal balance direction, and appends "
        "a final `is_grand_total=True` row proving Total Debits == Total Credits.\n\n"
        "`as_of_date` restricts to entries on or before that date (default: all "
        "posted history). `include_zero_balances=false` drops accounts with no "
        "activity."
    ),
    tags=["Accounting - Reports"],
    dependencies=[_FINANCE_ROLES],
)
async def get_trial_balance(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    as_of_date: date | None = Query(default=None),
    include_zero_balances: bool = Query(default=True),
) -> list[TrialBalanceRow]:
    rows = await generate_trial_balance(db, as_of_date=as_of_date, include_zero_balances=include_zero_balances)
    return [TrialBalanceRow.model_validate(r) for r in rows]


# ══════════════════════════════════════════════════════════════════
# FAILED GL POSTINGS — visibility + retry
# ══════════════════════════════════════════════════════════════════


@router.get(
    "/gl-postings/failed",
    summary="List automated postings that failed to reach the ledger",
    tags=["Accounting - GL Postings"],
    dependencies=[_FINANCE_ROLES],
)
async def list_failed_gl_postings(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> list[dict]:
    from sqlalchemy import select

    from app.modules.accounting.models.posting import GLPosting, GLPostingStatus

    rows = (
        await db.execute(
            select(GLPosting)
            .where(GLPosting.status == GLPostingStatus.FAILED)
            .order_by(GLPosting.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "entry_kind": r.entry_kind,
            "invoice_number": r.invoice_number,
            "amount": float(r.amount) if r.amount is not None else None,
            "error_type": r.error_type,
            "error_message": r.error_message,
            "attempts": r.attempts,
        }
        for r in rows
    ]


@router.post(
    "/gl-postings/{posting_id}/retry",
    summary="Retry a failed automated posting",
    tags=["Accounting - GL Postings"],
    dependencies=[_FINANCE_ROLES],
)
async def retry_failed_gl_posting(
    posting_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> dict:
    """Re-publishes the original invoice.created payload (kept in the outbox)
    with retry_failed=True. Idempotent: a posting that already succeeded is
    never posted twice (UNIQUE source/kind in gl_postings)."""
    from sqlalchemy import select

    from app.core.events.event_bus import DomainEvent
    from app.modules.accounting.events import handle_invoice_created
    from app.modules.accounting.models.posting import GLPosting, GLPostingStatus
    from app.modules.system.models import OutboxEvent

    posting = await db.get(GLPosting, posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail="Posting not found")
    if posting.status != GLPostingStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only FAILED postings can be retried")

    events = (
        await db.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.tenant_id == UUID(str(current_user.tenant_id)),
                OutboxEvent.event_type == "invoice.created",
            )
            .order_by(OutboxEvent.occurred_at.desc())
            .limit(500)
        )
    ).scalars().all()

    original: dict | None = None
    for ev in events:
        env = ev.payload or {}
        inner = env.get("payload") if isinstance(env.get("payload"), dict) else env
        if str(inner.get("source_id")) == str(posting.source_id) and (
            inner.get("entry_type") or inner.get("entry_kind")
        ) == posting.entry_kind:
            original = inner
            break
    if original is None:
        raise HTTPException(
            status_code=422,
            detail="Original event payload not found; re-run the business action instead.",
        )

    try:
        await handle_invoice_created(
            DomainEvent(
                event_type="invoice.created",
                tenant_id=str(current_user.tenant_id),
                payload={**original, "retry_failed": True},
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GL posting retry failed for %s", posting_id)
        raise HTTPException(status_code=502, detail=f"Retry failed: {exc}") from exc
    return {"status": "retried", "id": str(posting_id)}
