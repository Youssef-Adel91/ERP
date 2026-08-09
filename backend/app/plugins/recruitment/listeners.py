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

from app.core.db.database import AsyncSessionLocal
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.cases.models.core import Case, CaseStageHistory, CaseType

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
    tenant_id = str(ct.created_by) if hasattr(ct, "tenant_id") else "system"

    # We publish a synthetic invoice event so accounting creates the GL entry
    # without the recruitment plugin ever touching accounting tables.
    await event_bus.publish(
        InvoiceCreatedEvent(
            tenant_id=tenant_id,
            payload={
                "source": "recruitment_plugin",
                "source_id": str(case.id),
                "description": description,
                "amount": float(amount),
                "revenue_account_code": revenue_account,
                "receivable_account_code": "1200",
                "entry_date": date.today().isoformat(),
                "case_stage": stage,
            },
        ),
        session=session,
    )

    # Mark as posted in case.data (patch will be persisted by caller)
    case.data = {
        **case.data,
        flag_field: True,
        amount_field: float(amount),
    }
    session.add(case)
    logger.info(
        "Commission/fee GL post queued for case %s (stage: %s, amount: %s)",
        case.id, stage, amount,
    )


@event_bus.subscribe("case.stage.transitioned")
async def handle_stage_transitioned(event: DomainEvent) -> None:
    """
    Listens for ALL case stage transitions but acts only on:
      - plugin_key == "recruitment"
      - to_stage in ("contracted", "deployed")
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

    async with AsyncSessionLocal() as session:
        try:
            # Reconstruct tenant schema context
            tenant_id = event.tenant_id
            tenant_schema = f"tenant_{tenant_id.replace('-', '')}"
            await session.execute(f"SET search_path TO {tenant_schema}")

            case = await session.get(Case, UUID(case_id_str))
            if not case:
                logger.warning("Recruitment listener: Case %s not found", case_id_str)
                return

            ct = await session.get(CaseType, case.case_type_id)
            if not ct:
                logger.warning("Recruitment listener: CaseType not found for case %s", case_id_str)
                return

            await _post_commission_to_gl(session, case, ct, to_stage)
            await session.commit()
            logger.info(
                "Recruitment financial hook completed for case %s → stage %s",
                case_id_str, to_stage,
            )

        except Exception:
            logger.exception(
                "Recruitment listener failed for case %s stage %s",
                case_id_str, to_stage,
            )
            await session.rollback()
