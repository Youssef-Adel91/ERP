"""
app/plugins/recruitment/listeners.py — Financial Event Hooks

Subscribes to CaseStageTransitionedEvent from the core Case Engine.
When a candidate reaches "contracted" or "deployed", automatically posts
an agency commission or deployment fee to the General Ledger.

DECOUPLING CONTRACT:
  ✅ Listens on the EventBus — zero coupling to the transition trigger
  ✅ Reads GL account codes from CaseType.meta (plugin-defined config)
  ✅ Constructs and emits an InvoiceCreatedEvent to trigger accounting
     (never calls JournalEntry service directly)
  ❌ Never imports from app.modules.accounting directly
  ❌ Never imports from app.modules.cases.services.engine
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.cases.models.core import Case, CaseType

logger = logging.getLogger(__name__)
event_bus = get_event_bus()

# Stages that trigger a financial posting
_COMMISSION_TRIGGER_STAGE = "contracted"
_DEPLOYMENT_FEE_TRIGGER_STAGE = "deployed"


async def _post_commission_to_gl(
    session,
    case: Case,
    ct: CaseType,
    stage: str,
    tenant_id: str,
) -> None:
    """
    Publishes an internal event that the accounting module's handler picks
    up to create the double-entry Journal Entry. Never touches GL tables directly.

    Commission logic:
      - Amount = case.data["salary"] * commission_rate_from_meta
      - DR: Accounts Receivable (1200)
      - CR: Agency Commission Revenue (from CaseType.meta["commission_gl_account"])
    """
    salary = Decimal(str(case.data.get("salary", "0") or "0"))
    meta = ct.meta or {}

    if stage == _COMMISSION_TRIGGER_STAGE:
        rate = Decimal(str(meta.get("commission_rate_default", "0.10")))
        amount = (salary * rate).quantize(Decimal("0.01"))
        description = f"Agency commission — {case.title or str(case.id)}"
        revenue_account = meta.get("commission_gl_account", "4010")
        flag_field = "commission_posted"
        amount_field = "commission_amount"
    else:
        # deployed — flat deployment/processing fee (stored in meta or case.data)
        amount = Decimal(str(case.data.get("deployment_fee", meta.get("deployment_fee_default", "500")) or "500"))
        description = f"Deployment processing fee — {case.title or str(case.id)}"
        revenue_account = meta.get("deployment_fee_gl_account", "4010")
        flag_field = "deployment_fee_posted"
        amount_field = "deployment_fee_amount"

    if amount <= 0:
        logger.info("Zero commission/fee for case %s — skipping GL post", case.id)
        return

    if case.data.get(flag_field):
        logger.info("GL posting already made for case %s stage %s — idempotent skip", case.id, stage)
        return

    # Publish InvoiceCreatedEvent — the accounting module's handler creates
    # the JournalEntry (DR Accounts Receivable / CR Revenue Account)
    from app.core.events.event_bus import InvoiceCreatedEvent

    # Clear any stale failure flag from a previous attempt before retrying —
    # a successful post below should not leave a dangling "posting_failed".
    updated_data = {**case.data}
    updated_data.pop("posting_failed", None)
    updated_data.pop("posting_error", None)

    # NOTE: app/modules/accounting/events.py's handle_invoice_created() —
    # the ONLY subscriber of "invoice.created" — requires "invoice_number"
    # and "amount" in the payload (it silently aborts with a logged error,
    # never raises, if either is missing) and reads the AR account code
    # from "ar_account_code" (NOT "receivable_account_code" — that key is
    # kept below too since other tooling may read it, but the handler
    # itself ignores it and falls back to its own "1200" default unless
    # ar_account_code is present). Discovered via live verification: case
    # flags (commission_posted, etc.) were set to True by this listener
    # even though the downstream JournalEntry was silently never created —
    # the flag only reflects that WE published the event, not that
    # accounting successfully processed it.
    invoice_number = f"REC-{case.id.hex[:8].upper()}-{stage.upper()}"
    customer_name = (
        case.data.get("guarantor_company_name")
        or case.data.get("sponsor_company_name")
        or case.title
        or str(case.id)
    )
    await event_bus.publish(
        InvoiceCreatedEvent(
            tenant_id=tenant_id,
            payload={
                "source": "recruitment_plugin",
                "source_id": str(case.id),
                "invoice_id": str(case.id),
                "invoice_number": invoice_number,
                "customer_name": customer_name,
                "description": description,
                "amount": float(amount),
                "revenue_account_code": revenue_account,
                "receivable_account_code": "1200",
                "ar_account_code": "1200",
                "entry_date": date.today().isoformat(),
                "case_stage": stage,
            },
        ),
        session=session,
    )

    # Mark as posted in case.data (persisted by caller's commit)
    case.data = {
        **updated_data,
        flag_field: True,
        amount_field: float(amount),
    }
    session.add(case)
    logger.info(
        "Commission/fee GL post queued for case %s (stage: %s, amount: %s)",
        case.id, stage, amount,
    )


async def _mark_posting_failed(tenant_id: str, case_id_str: str, to_stage: str, exc: Exception) -> None:
    """Best-effort, separate-connection write of the posting_failed flag —
    used whenever we can't trust the session that just raised (it may be in
    a broken state) or don't have one at all."""
    try:
        async with tenant_session(tenant_id) as fail_session:
            failed_case = await fail_session.get(Case, UUID(case_id_str))
            if failed_case:
                failed_case.data = {
                    **failed_case.data,
                    "posting_failed": True,
                    "posting_error": f"{type(exc).__name__}: {exc}"[:500],
                    "posting_failed_stage": to_stage,
                }
                fail_session.add(failed_case)
    except Exception:
        logger.exception(
            "Recruitment listener: failed to mark posting_failed on case %s "
            "after the original posting error above.", case_id_str,
        )


@event_bus.subscribe("case.stage.transitioned")
async def handle_stage_transitioned(event: DomainEvent, session: AsyncSession | None = None) -> None:
    """
    Listens for ALL case stage transitions but acts only on:
      - plugin_key == "recruitment"
      - to_stage in ("contracted", "deployed")

    `session`: EventBus.publish() passes its caller's own session automatically
    whenever this handler's signature accepts a `session` kwarg (see
    app/core/events/event_bus.py's inspect.signature check) — and always
    swallows whatever this handler raises, so reusing that session here can
    never abort the publisher's own transaction.

    We MUST prefer that session over opening a fresh tenant_session() when
    one is available: app/modules/cases/services/engine.py's transition_case()
    only *flushes* the case's data changes (e.g. a `salary` field set in the
    very same API call that moves the case to "contracted") — the caller
    commits afterwards. A brand-new tenant_session() opens a separate DB
    connection/transaction, and under Postgres's default READ COMMITTED
    isolation it would NOT see those flushed-but-uncommitted changes,
    silently computing a zero commission. This was invisible before because
    the previous `SET search_path` bug crashed before ever reaching this
    calculation — fixing that bug exposed this next-level one.
    """
    payload = event.payload

    # Guard: only handle recruitment plugin events
    if payload.get("plugin_key") != "recruitment":
        return

    to_stage = payload.get("to_stage")
    if to_stage not in (_COMMISSION_TRIGGER_STAGE, _DEPLOYMENT_FEE_TRIGGER_STAGE):
        return

    case_id_str = payload.get("case_id")
    if not case_id_str:
        return

    tenant_id = event.tenant_id
    if not tenant_id:
        logger.warning(
            "Recruitment listener: event for case %s carries no tenant_id — cannot "
            "resolve tenant schema, skipping financial posting.", case_id_str,
        )
        return

    if session is not None:
        # Fast path — reuse the caller's already tenant-scoped session (it
        # came from get_tenant_db(), which itself uses tenant_session()'s
        # schema_translate_map, so schema resolution is still correct here).
        try:
            case = await session.get(Case, UUID(case_id_str))
            if not case:
                logger.warning("Recruitment listener: Case %s not found", case_id_str)
                return
            ct = await session.get(CaseType, case.case_type_id)
            if not ct:
                logger.warning("Recruitment listener: CaseType not found for case %s", case_id_str)
                return
            await _post_commission_to_gl(session, case, ct, to_stage, tenant_id)
            logger.info(
                "Recruitment financial hook completed for case %s → stage %s",
                case_id_str, to_stage,
            )
            # No manual commit/rollback — the caller owns this session's
            # transaction boundary (it commits after transition_case() returns).
        except Exception as exc:
            logger.exception(
                "Recruitment listener failed for case %s stage %s (shared-session "
                "path) — marking posting_failed on the case for visibility.",
                case_id_str, to_stage,
            )
            await _mark_posting_failed(tenant_id, case_id_str, to_stage, exc)
        return

    # Fallback path — no session was supplied (e.g. a future outbox-worker
    # driven dispatch, rather than the synchronous in-process EventBus path).
    # Use the SAME tenant-schema-isolation mechanism as every request handler
    # in this codebase (engine.execution_options(schema_translate_map=...) via
    # tenant_session()) — NOT a raw `SET search_path` string. A raw string
    # passed to AsyncSession.execute() is not an Executable and raises
    # ObjectNotExecutableError under SQLAlchemy 2.0 async; even wrapped in
    # text(), a manually-issued SET search_path on a pooled/asyncpg connection
    # is fragile and inconsistent with how every other schema-scoped query in
    # this app resolves the "tenant" placeholder schema. See the detailed
    # comment above tenant_session() in app/core/db/database.py, and the
    # "Step 2a" comment in the same file, for the full story of why
    # schema_translate_map is the only mechanism proven reliable here.
    try:
        async with tenant_session(tenant_id) as fresh_session:
            case = await fresh_session.get(Case, UUID(case_id_str))
            if not case:
                logger.warning("Recruitment listener: Case %s not found", case_id_str)
                return

            ct = await fresh_session.get(CaseType, case.case_type_id)
            if not ct:
                logger.warning("Recruitment listener: CaseType not found for case %s", case_id_str)
                return

            await _post_commission_to_gl(fresh_session, case, ct, to_stage, tenant_id)
            logger.info(
                "Recruitment financial hook completed for case %s → stage %s",
                case_id_str, to_stage,
            )
            # tenant_session() commits on clean exit and rolls back on
            # exception automatically — no manual commit/rollback needed here.

    except Exception as exc:
        # A silently-swallowed exception here previously meant a
        # commission/fee could fail to post to the GL with zero visibility
        # to anyone except someone manually reading backend.log. Surface the
        # failure ON THE CASE ITSELF (best-effort, separate transaction) so
        # it is visible in the UI/API, in addition to the log entry.
        logger.exception(
            "Recruitment listener failed for case %s stage %s — marking "
            "posting_failed on the case for visibility.",
            case_id_str, to_stage,
        )
        await _mark_posting_failed(tenant_id, case_id_str, to_stage, exc)
