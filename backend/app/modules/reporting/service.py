"""
app/modules/reporting/service.py — Typed Reporting Function Layer

This is Phase A of the AI roadmap (see the published roadmap artifact):
FR-1501 from the internal Phase 8 AI blueprint — "a reporting service
layer of typed functions, meant to be built for screens anyway, that the
AI Copilot sits on top of as an adapter, not a subsystem."

Every function here:
  - takes an already-tenant-scoped AsyncSession (from get_tenant_db — the
    schema_translate_map on that session is what makes it tenant-scoped,
    same as every other module in this codebase; there is no tenant_id
    parameter here because there's no tenant-scoped WHERE clause needed —
    schema isolation does that job)
  - returns a plain, JSON-serializable dict of REAL numbers straight from
    the ledger/tables — never a guess, never LLM-generated
  - is registered in REPORT_REGISTRY with a name, a one-line description,
    and a JSON-schema `parameters` block, so app.modules.ai.router can
    hand the whole registry to the LLM as "tools" for function-calling
    (Copilot Level 1: Grounded Retrieval — the model picks/fills one of
    these, never invents numbers itself; see the roadmap artifact §2 and
    the blueprint's non-negotiable guardrail #5: "every AI answer must
    drill through to source transactions, no exceptions").

This module is intentionally read-only. It must stay that way — see
app.core.ai.adapter's module docstring on guardrail #1.

Currently reuses/extends the exact same real (non-mocked) KPI queries
already live in app.modules.dashboard.router (see that module's own
docstring citing docs/Nexus_ERP_Audit_Report.md §15 — the mock-dashboard
fix this layer builds on) so the AI Bot's numbers and the dashboard's
numbers can never silently disagree; they're the same query.

Phase B additions (2026-09-11, see the published AI roadmap artifact):
get_revenue_trend and get_expense_breakdown power the dashboard's
"expanded dashboards" charts (app.modules.reporting.router — a new plain
REST surface for the frontend, distinct from REPORT_REGISTRY's
function-calling surface for the AI Bot) with the SAME functions the AI
Bot can also call — one source of numbers for both surfaces, same
guarantee as everything else in this file.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import public_session
from app.modules.accounting.models import (
    Account,
    AccountType,
    JournalEntry,
    JournalEntryStatus,
    TransactionLine,
)
from app.modules.contacts.models import Contact
from app.modules.sales.models.core import SalesOrder
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.modules.trust.services.gates import query_reputation


def _month_bounds(now: datetime) -> tuple[datetime, datetime, datetime]:
    start_this = datetime(now.year, now.month, 1, tzinfo=UTC)
    start_prev = (
        datetime(now.year - 1, 12, 1, tzinfo=UTC)
        if now.month == 1
        else datetime(now.year, now.month - 1, 1, tzinfo=UTC)
    )
    start_next = (
        datetime(now.year + 1, 1, 1, tzinfo=UTC)
        if now.month == 12
        else datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    )
    return start_this, start_prev, start_next


def _trend_pct(current: int | Decimal, previous: int | Decimal) -> float | None:
    if not previous:
        return None
    return round(float((current - previous) / previous) * 100, 1)


async def get_financial_summary(db: AsyncSession) -> dict[str, Any]:
    """Total revenue, receivables, payables, and cash balance — posted
    journal entries only. Identical query to
    app.modules.dashboard.router.get_dashboard_metrics's first four
    fields, so this can never drift from what the dashboard shows."""
    revenue = (
        await db.execute(
            select(func.coalesce(func.sum(TransactionLine.credit), Decimal("0")))
            .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.status == JournalEntryStatus.POSTED,
                TransactionLine.account_code.like("4%"),
            )
        )
    ).scalar_one() or Decimal("0")

    receivables = (
        await db.execute(
            select(func.coalesce(func.sum(TransactionLine.debit), Decimal("0")))
            .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.status == JournalEntryStatus.POSTED,
                TransactionLine.account_code == "1200",
            )
        )
    ).scalar_one() or Decimal("0")

    payables = (
        await db.execute(
            select(func.coalesce(func.sum(TransactionLine.credit), Decimal("0")))
            .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.status == JournalEntryStatus.POSTED,
                TransactionLine.account_code == "2100",
            )
        )
    ).scalar_one() or Decimal("0")

    cash_debit = (
        await db.execute(
            select(func.coalesce(func.sum(TransactionLine.debit), Decimal("0")))
            .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.status == JournalEntryStatus.POSTED,
                TransactionLine.account_code.like("11%"),
            )
        )
    ).scalar_one() or Decimal("0")
    cash_credit = (
        await db.execute(
            select(func.coalesce(func.sum(TransactionLine.credit), Decimal("0")))
            .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.status == JournalEntryStatus.POSTED,
                TransactionLine.account_code.like("11%"),
            )
        )
    ).scalar_one() or Decimal("0")

    return {
        "total_revenue_egp": float(revenue),
        "total_receivables_egp": float(receivables),
        "total_payables_egp": float(payables),
        "cash_balance_egp": float(cash_debit - cash_credit),
        "source": "posted journal_entries / transaction_lines (accounts 4xxx revenue, "
        "1200 AR, 2100 AP, 11xx cash)",
    }


async def get_sales_this_month_vs_last(db: AsyncSession) -> dict[str, Any]:
    """Order count and new-customer count, this calendar month vs. the
    previous one, with % trend. Same query as the dashboard's
    order_count/new_customers_count fields."""
    now = datetime.now(UTC)
    start_this, start_prev, _ = _month_bounds(now)

    orders_this = (
        await db.execute(
            select(func.count(SalesOrder.id)).where(SalesOrder.created_at >= start_this)
        )
    ).scalar_one()
    orders_prev = (
        await db.execute(
            select(func.count(SalesOrder.id)).where(
                SalesOrder.created_at >= start_prev, SalesOrder.created_at < start_this
            )
        )
    ).scalar_one()

    customers_this = (
        await db.execute(
            select(func.count(Contact.id)).where(Contact.created_at >= start_this)
        )
    ).scalar_one()
    customers_prev = (
        await db.execute(
            select(func.count(Contact.id)).where(
                Contact.created_at >= start_prev, Contact.created_at < start_this
            )
        )
    ).scalar_one()

    return {
        "orders_this_month": orders_this,
        "orders_trend_pct": _trend_pct(orders_this, orders_prev),
        "new_customers_this_month": customers_this,
        "new_customers_trend_pct": _trend_pct(customers_this, customers_prev),
        "source": "sales_orders / contacts, created_at grouped by calendar month",
    }


async def get_overdue_invoices(db: AsyncSession, limit: int = 20) -> dict[str, Any]:
    """The actual list of overdue POSTED sales invoices — same POSTED +
    due_date < today filter as
    app.modules.sales.services.reminders.process_overdue_reminders, so an
    AI answer about overdue invoices can never disagree with what the
    WhatsApp/email reminder engine is actually chasing."""
    today = date.today()
    result = await db.execute(
        select(SalesInvoice)
        .where(SalesInvoice.status == SalesInvoiceStatus.POSTED, SalesInvoice.due_date < today)
        .order_by(SalesInvoice.due_date.asc())
        .limit(limit)
    )
    invoices = result.scalars().all()

    contact_ids = {inv.contact_id for inv in invoices}
    contacts_by_id: dict[Any, str] = {}
    if contact_ids:
        contact_rows = await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))
        contacts_by_id = {c.id: c.name for c in contact_rows.scalars().all()}

    items = [
        {
            "invoice_number": inv.invoice_number,
            "customer_name": contacts_by_id.get(inv.contact_id, "غير معروف"),
            "due_date": inv.due_date.isoformat(),
            "days_overdue": (today - inv.due_date).days,
            "grand_total_egp": float(inv.grand_total),
            "currency": inv.currency,
        }
        for inv in invoices
    ]
    return {
        "count": len(items),
        "total_overdue_egp": round(sum(i["grand_total_egp"] for i in items), 2),
        "invoices": items,
        "source": "sales_invoices where status=POSTED and due_date < today, "
        f"limited to {limit} oldest-first",
    }


async def get_top_customers_by_revenue(db: AsyncSession, limit: int = 5) -> dict[str, Any]:
    """Top customers ranked by total POSTED invoice value — grounded
    entirely in sales_invoices, no estimation."""
    result = await db.execute(
        select(
            SalesInvoice.contact_id,
            func.sum(SalesInvoice.grand_total).label("total"),
            func.count(SalesInvoice.id).label("invoice_count"),
        )
        .where(SalesInvoice.status.in_([SalesInvoiceStatus.POSTED, SalesInvoiceStatus.PAID]))
        .group_by(SalesInvoice.contact_id)
        .order_by(func.sum(SalesInvoice.grand_total).desc())
        .limit(limit)
    )
    rows = result.all()

    contact_ids = [r.contact_id for r in rows]
    contacts_by_id: dict[Any, str] = {}
    if contact_ids:
        contact_rows = await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))
        contacts_by_id = {c.id: c.name for c in contact_rows.scalars().all()}

    return {
        "customers": [
            {
                "customer_name": contacts_by_id.get(r.contact_id, "غير معروف"),
                "total_billed_egp": float(r.total),
                "invoice_count": r.invoice_count,
            }
            for r in rows
        ],
        "source": "sales_invoices where status in (POSTED, PAID), grouped by contact_id, "
        f"top {limit} by total value",
    }


async def get_revenue_variance_analysis(db: AsyncSession) -> dict[str, Any]:
    """
    Copilot Level 2 (Deterministic Variance Decomposition — see the
    published AI roadmap artifact, and the internal Phase 8 blueprint's
    example "ليه مكسبي قل الشهر ده؟"). Deliberately NOT an LLM guess at
    "why revenue changed" — it's a real GROUP BY comparing this calendar
    month's invoiced revenue per customer against last month's, so the
    answer is a list of the actual customers who billed more or less,
    not a plausible-sounding story. The AI Bot narrates this data; it
    never invents the decomposition itself.

    Also splits the total into "from customers billed for the first time
    this month" vs "from customers who billed in both months" — a
    revenue drop hidden behind steady existing-customer billing but a
    stalled new-customer pipeline reads very differently from an existing
    customer churning, and a single top-line delta can't tell those
    apart.

    Coverage note: month boundaries are calendar-month, based on
    SalesInvoice.issue_date (not created_at) — the date the invoice was
    actually issued for, matching how a merchant thinks about "this
    month's revenue".
    """
    now = datetime.now(UTC)
    start_this, start_prev, start_next = _month_bounds(now)
    this_start_d, prev_start_d, next_start_d = (d.date() for d in (start_this, start_prev, start_next))

    async def _revenue_by_customer(start: date, end: date) -> dict[Any, Decimal]:
        rows = await db.execute(
            select(SalesInvoice.contact_id, func.sum(SalesInvoice.grand_total).label("total"))
            .where(
                SalesInvoice.status.in_([SalesInvoiceStatus.POSTED, SalesInvoiceStatus.PAID]),
                SalesInvoice.issue_date >= start,
                SalesInvoice.issue_date < end,
            )
            .group_by(SalesInvoice.contact_id)
        )
        return {r.contact_id: r.total for r in rows.all()}

    this_month = await _revenue_by_customer(this_start_d, next_start_d)
    last_month = await _revenue_by_customer(prev_start_d, this_start_d)

    this_total = sum(this_month.values(), Decimal("0"))
    last_total = sum(last_month.values(), Decimal("0"))

    new_this_month_ids = set(this_month) - set(last_month)
    returning_ids = set(this_month) & set(last_month)
    new_customers_revenue = sum((this_month[cid] for cid in new_this_month_ids), Decimal("0"))
    returning_customers_revenue_this = sum((this_month[cid] for cid in returning_ids), Decimal("0"))
    returning_customers_revenue_last = sum((last_month[cid] for cid in returning_ids), Decimal("0"))

    all_ids = set(this_month) | set(last_month)
    movers = sorted(
        (
            {
                "contact_id": cid,
                "this_month_egp": float(this_month.get(cid, Decimal("0"))),
                "last_month_egp": float(last_month.get(cid, Decimal("0"))),
                "delta_egp": float(this_month.get(cid, Decimal("0")) - last_month.get(cid, Decimal("0"))),
            }
            for cid in all_ids
        ),
        key=lambda m: abs(m["delta_egp"]),
        reverse=True,
    )[:5]

    contact_ids = {m["contact_id"] for m in movers}
    names_by_id: dict[Any, str] = {}
    if contact_ids:
        contact_rows = await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))
        names_by_id = {c.id: c.name for c in contact_rows.scalars().all()}
    for m in movers:
        m["customer_name"] = names_by_id.get(m.pop("contact_id"), "غير معروف")

    return {
        "this_month_revenue_egp": float(this_total),
        "last_month_revenue_egp": float(last_total),
        "delta_egp": float(this_total - last_total),
        "delta_pct": _trend_pct(this_total, last_total),
        "breakdown": {
            "new_customers_this_month_revenue_egp": float(new_customers_revenue),
            "returning_customers_this_month_revenue_egp": float(returning_customers_revenue_this),
            "returning_customers_last_month_revenue_egp": float(returning_customers_revenue_last),
        },
        "top_movers": movers,
        "source": "sales_invoices where status in (POSTED, PAID), grouped by contact_id and "
        "issue_date's calendar month, this month vs previous month",
    }


async def get_revenue_trend(db: AsyncSession, months: int = 6) -> dict[str, Any]:
    """
    Real monthly revenue for the last `months` calendar months (this
    month included), from posted journal entries' credit lines on
    revenue accounts (4xxx) — same account-code filter as
    get_financial_summary, so the current month's point on this trend can
    never disagree with that KPI card. Grouped in Python (not SQL
    date_trunc) to stay dialect-agnostic and keep the aggregation trivial
    to reason about for the small transaction volumes this reporting
    layer deals with.

    Powers the dashboard's "ترند الإيرادات" chart (Phase B) — replaces
    the honest "not wired up yet" placeholder that was there instead of a
    fabricated chart.
    """
    now = datetime.now(UTC)
    year, month = now.year, now.month
    month_starts: list[date] = []
    y, m = year, month
    for _ in range(max(1, months)):
        month_starts.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    month_starts.reverse()

    range_start = month_starts[0]
    end_year = year + (1 if month == 12 else 0)
    end_month = 1 if month == 12 else month + 1
    range_end = date(end_year, end_month, 1)

    rows = await db.execute(
        select(JournalEntry.entry_date, TransactionLine.credit)
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            TransactionLine.account_code.like("4%"),
            JournalEntry.entry_date >= range_start,
            JournalEntry.entry_date < range_end,
        )
    )

    totals: dict[tuple[int, int], Decimal] = {}
    for entry_date, credit in rows.all():
        key = (entry_date.year, entry_date.month)
        totals[key] = totals.get(key, Decimal("0")) + (credit or Decimal("0"))

    series = [
        {
            "month": ms.strftime("%Y-%m"),
            "revenue_egp": float(totals.get((ms.year, ms.month), Decimal("0"))),
        }
        for ms in month_starts
    ]
    return {
        "months": series,
        "source": "posted journal_entries credit lines on 4xxx (revenue) accounts, "
        f"grouped by entry_date's calendar month, last {months} months",
    }


async def get_expense_breakdown(db: AsyncSession) -> dict[str, Any]:
    """
    Real expense totals for the CURRENT calendar month, grouped by
    expense account (Account.account_type == EXPENSE), from posted
    journal entries' debit lines. Grounded entirely in the chart of
    accounts — an account only shows up here if a real transaction
    posted to it.

    Powers the dashboard's "توزيع المصروفات" chart (Phase B) — replaces
    the honest "not wired up yet" placeholder that was there instead of a
    fabricated chart.
    """
    now = datetime.now(UTC)
    start_this, _, start_next = _month_bounds(now)
    this_start_d, next_start_d = start_this.date(), start_next.date()

    rows = await db.execute(
        select(
            Account.code,
            Account.name,
            Account.name_ar,
            func.sum(TransactionLine.debit).label("total"),
        )
        .join(TransactionLine, TransactionLine.account_id == Account.id)
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            Account.account_type == AccountType.EXPENSE,
            JournalEntry.entry_date >= this_start_d,
            JournalEntry.entry_date < next_start_d,
        )
        .group_by(Account.code, Account.name, Account.name_ar)
        .order_by(func.sum(TransactionLine.debit).desc())
    )

    items = [
        {
            "account_code": code,
            "account_name": name_ar or name,
            "amount_egp": float(total or Decimal("0")),
        }
        for code, name, name_ar, total in rows.all()
    ]
    total_expenses = round(sum(i["amount_egp"] for i in items), 2)

    return {
        "total_expenses_egp": total_expenses,
        "items": items,
        "source": "posted journal_entries debit lines joined to accounts where "
        "account_type=EXPENSE, this calendar month, grouped by account",
    }


async def get_customer_trust_profile(db: AsyncSession, tenant_id: str, customer_name: str) -> dict[str, Any]:
    """
    Phase F (2026-09-11, AI roadmap — cross-tenant Trust Network
    intelligence): resolves a customer NAME to this tenant's own Contact
    record, then queries the real, pre-existing, gate-enforced cross-tenant
    Trust Network (app.modules.trust.services.gates.query_reputation) —
    the exact same engine behind the manual phone-lookup form on
    /dashboard/trust — for that contact's phone number.

    Never invents a score. If no contact matches, or the contact has no
    phone on file, or the reciprocity/K-anonymity gates block/mask the
    result, that is returned honestly (found: False, or band: UNKNOWN with
    an explanation) rather than fabricated.

    tenant_id is required here (unlike every other function in this file)
    because query_reputation enforces the Reciprocity Gate per-tenant and
    must run against the shared PUBLIC schema, not this tenant's schema —
    so this is the one report that needs an explicit tenant_id passed in
    (see app.modules.ai.service's REPORT_REGISTRY "needs_tenant_id" flag).
    """
    result = await db.execute(
        select(Contact).where(Contact.name.ilike(f"%{customer_name}%")).limit(1)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        return {
            "found": False,
            "message": f"لم يتم العثور على عميل بالاسم '{customer_name}' في جهات الاتصال.",
        }
    if not contact.phone:
        return {
            "found": True,
            "customer_name": contact.name,
            "band": "UNKNOWN",
            "explanation": "لا يوجد رقم هاتف مسجل لهذا العميل، فلا يمكن الاستعلام عن شبكة الثقة.",
            "distinct_tenant_count": 0,
        }
    try:
        async with public_session() as public_db:
            reputation = await query_reputation(public_db, tenant_id, contact.phone)
    except HTTPException as exc:
        return {
            "found": True,
            "customer_name": contact.name,
            "band": "UNKNOWN",
            "explanation": (
                "لا يمكن الاستعلام عن شبكة الثقة الآن: يجب المساهمة بنتيجة "
                "شحنة واحدة على الأقل خلال آخر 30 يومًا قبل الاستعلام "
                "(بوابة المعاملة بالمثل)."
                if exc.status_code == 403
                else str(exc.detail)
            ),
            "distinct_tenant_count": 0,
        }
    return {
        "found": True,
        "customer_name": contact.name,
        "band": reputation["band"],
        "explanation": reputation["explanation"],
        "distinct_tenant_count": reputation["distinct_tenant_count"],
        "source": (
            "app.modules.trust.services.gates.query_reputation — نفس محرك "
            "شبكة الثقة المستخدم في صفحة 'شبكة الثقة'، بعد حل اسم العميل "
            "لرقم هاتفه داخل بيانات هذا التاجر."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────
# Registry: what app.modules.ai.router exposes to the LLM as "tools" for
# function-calling. Keep descriptions short and literal — the model reads
# these to decide which one answers the user's question.
# ─────────────────────────────────────────────────────────────────────────
REPORT_REGISTRY: dict[str, dict[str, Any]] = {
    "get_financial_summary": {
        "fn": get_financial_summary,
        "description": (
            "إجمالي الإيرادات والمديونيات (المستحق للتحصيل من العملاء) والمستحق "
            "للدفع للموردين والرصيد النقدي — أرقام حقيقية من دفتر الأستاذ العام."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "get_sales_this_month_vs_last": {
        "fn": get_sales_this_month_vs_last,
        "description": (
            "عدد الطلبات وعدد العملاء الجدد هذا الشهر، مقارنة بالشهر الماضي، "
            "مع نسبة التغيير."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "get_overdue_invoices": {
        "fn": get_overdue_invoices,
        "description": (
            "قائمة الفواتير المتأخرة عن السداد (تجاوزت تاريخ الاستحقاق ولم تُدفع بعد)، "
            "مع اسم العميل والمبلغ وعدد أيام التأخير."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "أقصى عدد فواتير يتم إرجاعها (افتراضي 20)",
                }
            },
            "required": [],
        },
    },
    "get_top_customers_by_revenue": {
        "fn": get_top_customers_by_revenue,
        "description": "أكبر العملاء من حيث إجمالي قيمة الفواتير المُرحّلة أو المدفوعة.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "عدد العملاء المطلوب إرجاعهم (افتراضي 5)",
                }
            },
            "required": [],
        },
    },
    "get_revenue_variance_analysis": {
        "fn": get_revenue_variance_analysis,
        "description": (
            "تحليل سبب تغيّر الإيرادات هذا الشهر مقارنة بالشهر الماضي: الفرق بالجنيه "
            "والنسبة، وتقسيمه إلى إيرادات من عملاء جدد مقابل عملاء متكررين، وأكبر "
            "العملاء اللي زادت أو قلّت فواتيرهم — مفيد لسؤال زي 'ليه الإيرادات اتغيرت؟'."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "get_revenue_trend": {
        "fn": get_revenue_trend,
        "description": (
            "ترند الإيرادات الشهرية على مدار عدد من الأشهر الماضية (افتراضي 6 أشهر) — "
            "مفيد لسؤال زي 'ازاي الإيرادات بتتحرك على مدار الوقت؟'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "عدد الأشهر المطلوب إرجاعها (افتراضي 6)",
                }
            },
            "required": [],
        },
    },
    "get_expense_breakdown": {
        "fn": get_expense_breakdown,
        "description": (
            "توزيع المصروفات هذا الشهر حسب نوع الحساب (تكلفة البضاعة المباعة، "
            "مصروفات تشغيلية، إلخ) — أرقام حقيقية من القيود المرحّلة."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "get_customer_trust_profile": {
        "fn": get_customer_trust_profile,
        "needs_tenant_id": True,
        "description": (
            "تقييم الثقة/المخاطرة لعميل معين بالاسم عبر شبكة الثقة (Trust Network) "
            "التي تجمع تقييمات من تجار آخرين — مفيد لسؤال زي 'هل العميل أحمد موثوق؟' "
            "أو 'إيه تقييم شحن العميل فلان؟'. يبحث عن العميل في جهات الاتصال الخاصة "
            "بهذا التاجر أولاً، ثم يستعلم عن رقم هاتفه في الشبكة."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "اسم العميل (كامل أو جزء منه) المطلوب الاستعلام عن تقييمه",
                }
            },
            "required": ["customer_name"],
        },
    },
}
