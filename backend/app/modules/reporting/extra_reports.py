"""
app/modules/reporting/extra_reports.py — AI-ready report catalogue (Phase C)

Adds ~15 typed, read-only reports on top of the original REPORT_REGISTRY so
the AI assistant (and the "report catalogue" UI) can answer almost any
financial / sales / inventory question, and so every answer can be
downloaded as Excel/CSV.

Contract shared by every report here (and normalised for the legacy ones in
app.modules.reporting.tabular):

    {
      "title":   "<Arabic title>",
      "period":  {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"} | None,
      "summary": {"<Arabic label>": number | str, ...},
      "columns": [{"key": "...", "label": "<Arabic>", "type": "text|money|number|date|percent"}],
      "rows":    [{...}],
      "source":  "<where the numbers come from>"
    }

All numbers come from posted ledger entries or the operational tables —
never from the model. Read-only by construction (no session.add/commit).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models import Account, JournalEntry, JournalEntryStatus, TransactionLine
from app.modules.contacts.models import Contact
from app.modules.finance.models.cheques import Cheque, ChequeStatus
from app.modules.hr.models.core import Employee, Payslip, PayslipStatus
from app.modules.inventory.models.core import Item, StockLevel
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceLine, SalesInvoiceStatus

ZERO = Decimal("0")


# ── helpers ──────────────────────────────────────────────────────────────────


def _f(v: Any) -> float:
    return round(float(v or 0), 2)


def _parse(v: str | date | None, default: date) -> date:
    if isinstance(v, date):
        return v
    if not v:
        return default
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return default


def _period(date_from: str | None, date_to: str | None) -> tuple[date, date]:
    today = date.today()
    start = _parse(date_from, today.replace(day=1))
    end = _parse(date_to, today)
    if end < start:
        start, end = end, start
    return start, end


def _table(
    title: str,
    columns: list[tuple[str, str, str]],
    rows: list[dict[str, Any]],
    summary: dict[str, Any] | None = None,
    source: str = "",
    period: tuple[date, date] | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "period": {"from": period[0].isoformat(), "to": period[1].isoformat()} if period else None,
        "summary": summary or {},
        "columns": [{"key": k, "label": label, "type": t} for k, label, t in columns],
        "rows": rows,
        "count": len(rows),
        "source": source,
    }


async def _ledger(
    db: AsyncSession, date_from: date | None, date_to: date | None, prefix: str | None = None, code: str | None = None
):
    """Posted ledger totals grouped by account code for a date window."""
    q = (
        select(
            TransactionLine.account_code,
            func.coalesce(func.sum(TransactionLine.debit), ZERO),
            func.coalesce(func.sum(TransactionLine.credit), ZERO),
        )
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(JournalEntry.status == JournalEntryStatus.POSTED)
        .group_by(TransactionLine.account_code)
        .order_by(TransactionLine.account_code)
    )
    if date_from:
        q = q.where(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.where(JournalEntry.entry_date <= date_to)
    if prefix:
        q = q.where(TransactionLine.account_code.like(f"{prefix}%"))
    if code:
        q = q.where(TransactionLine.account_code == code)
    return (await db.execute(q)).all()


async def _names(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(select(Account.code, Account.name_ar, Account.name))).all()
    return {c: (ar or n) for c, ar, n in rows}


async def _contact_names(db: AsyncSession, ids: set) -> dict:
    if not ids:
        return {}
    rows = (await db.execute(select(Contact.id, Contact.name).where(Contact.id.in_(ids)))).all()
    return {i: n for i, n in rows}


# ── financial statements ─────────────────────────────────────────────────────


async def get_profit_and_loss(db: AsyncSession, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to)
    names = await _names(db)
    rows, revenue, cogs, opex = [], ZERO, ZERO, ZERO
    for code, dr, cr in await _ledger(db, start, end):
        if code.startswith("4"):
            amt = cr - dr
            revenue += amt
            kind = "إيرادات"
        elif code.startswith("5"):
            amt = dr - cr
            if code.startswith("501"):
                cogs += amt
                kind = "تكلفة المبيعات"
            else:
                opex += amt
                kind = "مصروفات"
        else:
            continue
        rows.append({"code": code, "account": names.get(code, code), "kind": kind, "amount": _f(amt)})
    gross = revenue - cogs
    net = gross - opex
    return _table(
        "قائمة الدخل (الأرباح والخسائر)",
        [("code", "الكود", "text"), ("account", "الحساب", "text"), ("kind", "النوع", "text"), ("amount", "المبلغ", "money")],
        rows,
        {
            "إجمالي الإيرادات": _f(revenue),
            "تكلفة المبيعات": _f(cogs),
            "مجمل الربح": _f(gross),
            "المصروفات التشغيلية": _f(opex),
            "صافي الربح": _f(net),
            "هامش صافي الربح %": round(float(net / revenue * 100), 1) if revenue else 0,
        },
        "قيود مرحّلة (POSTED) — حسابات 4xxx إيرادات و5xxx تكلفة/مصروفات",
        (start, end),
    )


async def get_balance_sheet(db: AsyncSession, as_of: str | None = None) -> dict:
    end = _parse(as_of, date.today())
    names = await _names(db)
    rows, assets, liab, equity, income = [], ZERO, ZERO, ZERO, ZERO
    for code, dr, cr in await _ledger(db, None, end):
        if code.startswith("1"):
            amt, kind = dr - cr, "أصول"
            assets += amt
        elif code.startswith("2"):
            amt, kind = cr - dr, "خصوم"
            liab += amt
        elif code.startswith("3"):
            amt, kind = cr - dr, "حقوق ملكية"
            equity += amt
        else:
            income += (cr - dr) if code.startswith("4") else -(dr - cr)
            continue
        rows.append({"code": code, "account": names.get(code, code), "kind": kind, "amount": _f(amt)})
    rows.append({"code": "—", "account": "أرباح الفترة المرحّلة (صافي الدخل)", "kind": "حقوق ملكية", "amount": _f(income)})
    total_eq = equity + income
    return _table(
        "الميزانية العمومية",
        [("code", "الكود", "text"), ("account", "الحساب", "text"), ("kind", "النوع", "text"), ("amount", "المبلغ", "money")],
        rows,
        {
            "إجمالي الأصول": _f(assets),
            "إجمالي الخصوم": _f(liab),
            "إجمالي حقوق الملكية": _f(total_eq),
            "الخصوم + حقوق الملكية": _f(liab + total_eq),
            "الميزانية متوازنة": "نعم" if abs(assets - liab - total_eq) < Decimal("0.01") else "لا",
        },
        "قيود مرحّلة حتى تاريخ المركز المالي",
        None,
    ) | {"as_of": end.isoformat()}


async def get_trial_balance_report(db: AsyncSession, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to)
    names = await _names(db)
    rows, td, tc = [], ZERO, ZERO
    for code, dr, cr in await _ledger(db, start, end):
        td += dr
        tc += cr
        rows.append({"code": code, "account": names.get(code, code), "debit": _f(dr), "credit": _f(cr), "balance": _f(dr - cr)})
    return _table(
        "ميزان المراجعة",
        [("code", "الكود", "text"), ("account", "الحساب", "text"), ("debit", "مدين", "money"), ("credit", "دائن", "money"), ("balance", "الرصيد", "money")],
        rows,
        {"إجمالي المدين": _f(td), "إجمالي الدائن": _f(tc), "متوازن": "نعم" if abs(td - tc) < Decimal("0.01") else "لا"},
        "قيود مرحّلة (POSTED)",
        (start, end),
    )


async def get_vat_summary(db: AsyncSession, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to)
    rows_l = await _ledger(db, start, end, code="2200")
    dr = sum((r[1] for r in rows_l), ZERO)
    cr = sum((r[2] for r in rows_l), ZERO)
    inv = (
        await db.execute(
            select(func.count(SalesInvoice.id), func.coalesce(func.sum(SalesInvoice.subtotal), ZERO), func.coalesce(func.sum(SalesInvoice.tax_total), ZERO))
            .where(SalesInvoice.status.in_([SalesInvoiceStatus.POSTED, SalesInvoiceStatus.PAID]), SalesInvoice.issue_date.between(start, end))
        )
    ).one()
    rows = [
        {"item": "ضريبة مُحصّلة على المبيعات (دائن 2200)", "amount": _f(cr)},
        {"item": "ضريبة مُستردة/مرتجعات (مدين 2200)", "amount": _f(dr)},
        {"item": "صافي الضريبة المستحقة للسداد", "amount": _f(cr - dr)},
    ]
    return _table(
        "ملخص ضريبة القيمة المضافة",
        [("item", "البند", "text"), ("amount", "المبلغ", "money")],
        rows,
        {"عدد الفواتير": int(inv[0]), "صافي المبيعات الخاضعة": _f(inv[1]), "ضريبة الفواتير": _f(inv[2]), "صافي الضريبة المستحقة": _f(cr - dr)},
        "حساب 2200 + فواتير المبيعات المرحّلة/المدفوعة",
        (start, end),
    )


async def get_cash_flow(db: AsyncSession, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to)
    q = (
        select(
            func.date_trunc("month", JournalEntry.entry_date).label("m"),
            func.coalesce(func.sum(TransactionLine.debit), ZERO),
            func.coalesce(func.sum(TransactionLine.credit), ZERO),
        )
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            TransactionLine.account_code.like("11%"),
            JournalEntry.entry_date.between(start, end),
        )
        .group_by("m")
        .order_by("m")
    )
    rows, tin, tout = [], ZERO, ZERO
    for m, dr, cr in (await db.execute(q)).all():
        tin += dr
        tout += cr
        rows.append({"month": m.strftime("%Y-%m"), "inflow": _f(dr), "outflow": _f(cr), "net": _f(dr - cr)})
    opening = sum((r[1] - r[2] for r in await _ledger(db, None, start - timedelta(days=1), prefix="11")), ZERO)
    return _table(
        "التدفقات النقدية",
        [("month", "الشهر", "text"), ("inflow", "المقبوضات", "money"), ("outflow", "المدفوعات", "money"), ("net", "الصافي", "money")],
        rows,
        {"رصيد أول الفترة": _f(opening), "إجمالي المقبوضات": _f(tin), "إجمالي المدفوعات": _f(tout), "صافي التدفق": _f(tin - tout), "رصيد آخر الفترة": _f(opening + tin - tout)},
        "حسابات النقدية 11xx من القيود المرحّلة",
        (start, end),
    )


async def get_account_ledger(db: AsyncSession, account_code: str, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to)
    names = await _names(db)
    opening = sum((r[1] - r[2] for r in await _ledger(db, None, start - timedelta(days=1), code=account_code)), ZERO)
    q = (
        select(JournalEntry.entry_date, JournalEntry.reference, JournalEntry.description, TransactionLine.debit, TransactionLine.credit)
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            TransactionLine.account_code == account_code,
            JournalEntry.entry_date.between(start, end),
        )
        .order_by(JournalEntry.entry_date, JournalEntry.created_at)
        .limit(2000)
    )
    rows, bal = [], opening
    for d, ref, desc, dr, cr in (await db.execute(q)).all():
        bal += (dr or ZERO) - (cr or ZERO)
        rows.append({"date": d.isoformat(), "reference": ref or "", "description": desc, "debit": _f(dr), "credit": _f(cr), "balance": _f(bal)})
    return _table(
        f"كشف حساب {account_code} — {names.get(account_code, '')}".strip(" —"),
        [("date", "التاريخ", "date"), ("reference", "المرجع", "text"), ("description", "البيان", "text"), ("debit", "مدين", "money"), ("credit", "دائن", "money"), ("balance", "الرصيد", "money")],
        rows,
        {"رصيد أول المدة": _f(opening), "رصيد آخر المدة": _f(bal), "عدد الحركات": len(rows)},
        "قيود مرحّلة على هذا الحساب",
        (start, end),
    )


# ── sales / receivables ──────────────────────────────────────────────────────

_BUCKETS = [("غير مستحقة بعد", None, 0), ("1–30 يوم", 1, 30), ("31–60 يوم", 31, 60), ("61–90 يوم", 61, 90), ("أكثر من 90 يوم", 91, 10**6)]


async def get_ar_aging(db: AsyncSession) -> dict:
    today = date.today()
    invs = (await db.execute(select(SalesInvoice).where(SalesInvoice.status == SalesInvoiceStatus.POSTED).order_by(SalesInvoice.due_date))).scalars().all()
    names = await _contact_names(db, {i.contact_id for i in invs})
    totals = {b[0]: ZERO for b in _BUCKETS}
    rows = []
    for i in invs:
        late = (today - i.due_date).days
        label = _BUCKETS[0][0] if late <= 0 else next(b[0] for b in _BUCKETS[1:] if b[1] <= late <= b[2])
        totals[label] += i.grand_total
        rows.append({"invoice": i.invoice_number, "customer": names.get(i.contact_id, "غير معروف"), "due_date": i.due_date.isoformat(), "days_late": max(late, 0), "bucket": label, "amount": _f(i.grand_total)})
    summary = {k: _f(v) for k, v in totals.items()}
    summary["الإجمالي المستحق"] = _f(sum(totals.values(), ZERO))
    return _table(
        "أعمار الديون (العملاء)",
        [("invoice", "الفاتورة", "text"), ("customer", "العميل", "text"), ("due_date", "الاستحقاق", "date"), ("days_late", "أيام التأخير", "number"), ("bucket", "الفئة", "text"), ("amount", "المبلغ", "money")],
        rows,
        summary,
        "فواتير المبيعات المرحّلة غير المدفوعة",
    )


async def get_sales_by_customer(db: AsyncSession, date_from: str | None = None, date_to: str | None = None, limit: int = 20) -> dict:
    start, end = _period(date_from, date_to)
    q = (
        select(SalesInvoice.contact_id, func.count(SalesInvoice.id), func.coalesce(func.sum(SalesInvoice.grand_total), ZERO))
        .where(SalesInvoice.status.in_([SalesInvoiceStatus.POSTED, SalesInvoiceStatus.PAID]), SalesInvoice.issue_date.between(start, end))
        .group_by(SalesInvoice.contact_id)
        .order_by(func.sum(SalesInvoice.grand_total).desc())
        .limit(max(1, min(limit, 200)))
    )
    data = (await db.execute(q)).all()
    names = await _contact_names(db, {r[0] for r in data})
    rows = [{"customer": names.get(c, "غير معروف"), "invoices": int(n), "total": _f(t)} for c, n, t in data]
    return _table(
        "المبيعات حسب العميل",
        [("customer", "العميل", "text"), ("invoices", "عدد الفواتير", "number"), ("total", "إجمالي المبيعات", "money")],
        rows,
        {"إجمالي المبيعات": _f(sum((Decimal(str(r["total"])) for r in rows), ZERO)), "عدد العملاء": len(rows)},
        "فواتير مرحّلة/مدفوعة",
        (start, end),
    )


async def get_top_selling_items(db: AsyncSession, date_from: str | None = None, date_to: str | None = None, limit: int = 10) -> dict:
    start, end = _period(date_from, date_to)
    q = (
        select(Item.sku, Item.name, func.sum(SalesInvoiceLine.qty), func.sum(SalesInvoiceLine.line_total))
        .join(SalesInvoice, SalesInvoiceLine.invoice_id == SalesInvoice.id)
        .join(Item, Item.id == SalesInvoiceLine.item_id)
        .where(SalesInvoice.status.in_([SalesInvoiceStatus.POSTED, SalesInvoiceStatus.PAID]), SalesInvoice.issue_date.between(start, end))
        .group_by(Item.sku, Item.name)
        .order_by(func.sum(SalesInvoiceLine.line_total).desc())
        .limit(max(1, min(limit, 200)))
    )
    rows = [{"sku": s, "item": n, "qty": _f(qty), "revenue": _f(rev)} for s, n, qty, rev in (await db.execute(q)).all()]
    return _table(
        "الأصناف الأكثر مبيعًا",
        [("sku", "الكود", "text"), ("item", "الصنف", "text"), ("qty", "الكمية", "number"), ("revenue", "الإيراد", "money")],
        rows,
        {"عدد الأصناف": len(rows), "إجمالي الإيراد": _f(sum((Decimal(str(r["revenue"])) for r in rows), ZERO))},
        "بنود فواتير المبيعات المرحّلة/المدفوعة",
        (start, end),
    )


async def get_daily_sales(db: AsyncSession, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to)
    q = (
        select(SalesInvoice.issue_date, func.count(SalesInvoice.id), func.sum(SalesInvoice.subtotal), func.sum(SalesInvoice.tax_total), func.sum(SalesInvoice.grand_total))
        .where(SalesInvoice.status.in_([SalesInvoiceStatus.POSTED, SalesInvoiceStatus.PAID]), SalesInvoice.issue_date.between(start, end))
        .group_by(SalesInvoice.issue_date)
        .order_by(SalesInvoice.issue_date)
    )
    rows = [{"date": d.isoformat(), "invoices": int(n), "subtotal": _f(s), "tax": _f(t), "total": _f(g)} for d, n, s, t, g in (await db.execute(q)).all()]
    return _table(
        "المبيعات اليومية",
        [("date", "التاريخ", "date"), ("invoices", "الفواتير", "number"), ("subtotal", "قبل الضريبة", "money"), ("tax", "الضريبة", "money"), ("total", "الإجمالي", "money")],
        rows,
        {"إجمالي المبيعات": round(sum(r["total"] for r in rows), 2), "عدد الفواتير": sum(r["invoices"] for r in rows), "متوسط يومي": round(sum(r["total"] for r in rows) / len(rows), 2) if rows else 0},
        "فواتير مرحّلة/مدفوعة",
        (start, end),
    )


async def get_customer_statement(db: AsyncSession, customer_name: str, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to or None)
    if not date_from:
        start = date(2000, 1, 1)
    c = (await db.execute(select(Contact).where(Contact.name.ilike(f"%{customer_name.strip()}%")).limit(1))).scalar_one_or_none()
    if c is None:
        return _table("كشف حساب عميل", [("note", "ملاحظة", "text")], [{"note": f"لا يوجد عميل باسم «{customer_name}»"}], {}, "جهات الاتصال")
    invs = (
        await db.execute(
            select(SalesInvoice).where(SalesInvoice.contact_id == c.id, SalesInvoice.status != SalesInvoiceStatus.CANCELLED, SalesInvoice.issue_date.between(start, end)).order_by(SalesInvoice.issue_date)
        )
    ).scalars().all()
    rows = [{"date": i.issue_date.isoformat(), "invoice": i.invoice_number, "status": i.status.value, "total": _f(i.grand_total)} for i in invs]
    outstanding = sum((i.grand_total for i in invs if i.status == SalesInvoiceStatus.POSTED), ZERO)
    return _table(
        f"كشف حساب العميل: {c.name}",
        [("date", "التاريخ", "date"), ("invoice", "الفاتورة", "text"), ("status", "الحالة", "text"), ("total", "الإجمالي", "money")],
        rows,
        {"العميل": c.name, "إجمالي الفواتير": _f(sum((i.grand_total for i in invs), ZERO)), "المستحق (غير مدفوع)": _f(outstanding), "عدد الفواتير": len(invs)},
        "فواتير المبيعات للعميل",
        (start, end),
    )


# ── finance / inventory / HR ─────────────────────────────────────────────────


async def get_cheques_due(db: AsyncSession, days: int = 30) -> dict:
    today = date.today()
    horizon = today + timedelta(days=max(0, min(days, 365)))
    chq = (
        await db.execute(
            select(Cheque).where(Cheque.status.in_([ChequeStatus.PENDING, ChequeStatus.DEPOSITED]), Cheque.due_date <= horizon).order_by(Cheque.due_date)
        )
    ).scalars().all()
    names = await _contact_names(db, {c.contact_id for c in chq})
    rows = [
        {
            "cheque": c.cheque_number,
            "direction": "وارد" if c.cheque_type.value == "incoming" else "صادر",
            "party": names.get(c.contact_id, "غير معروف"),
            "bank": c.bank_name,
            "due_date": c.due_date.isoformat(),
            "state": "متأخر" if c.due_date < today else "قادم",
            "amount": _f(c.amount),
        }
        for c in chq
    ]
    inc = sum((c.amount for c in chq if c.cheque_type.value == "incoming"), ZERO)
    out = sum((c.amount for c in chq if c.cheque_type.value == "outgoing"), ZERO)
    return _table(
        "الشيكات المستحقة",
        [("cheque", "رقم الشيك", "text"), ("direction", "النوع", "text"), ("party", "الطرف", "text"), ("bank", "البنك", "text"), ("due_date", "الاستحقاق", "date"), ("state", "الحالة", "text"), ("amount", "المبلغ", "money")],
        rows,
        {"شيكات واردة مستحقة": _f(inc), "شيكات صادرة مستحقة": _f(out), "العدد": len(rows)},
        f"شيكات معلّقة/مودعة تستحق خلال {days} يوم",
    )


async def get_low_stock(db: AsyncSession, threshold: int = 5) -> dict:
    q = (
        select(Item.sku, Item.name, func.coalesce(func.sum(StockLevel.quantity), ZERO).label("qty"))
        .outerjoin(StockLevel, StockLevel.item_id == Item.id)
        .group_by(Item.sku, Item.name)
        .having(func.coalesce(func.sum(StockLevel.quantity), ZERO) <= threshold)
        .order_by("qty")
        .limit(500)
    )
    rows = [{"sku": s, "item": n, "qty": _f(q_)} for s, n, q_ in (await db.execute(q)).all()]
    return _table(
        "أصناف المخزون المنخفض",
        [("sku", "الكود", "text"), ("item", "الصنف", "text"), ("qty", "الكمية المتاحة", "number")],
        rows,
        {"عدد الأصناف": len(rows), "الحد الأدنى المستخدم": threshold},
        "مستويات المخزون الحالية",
    )


async def get_stock_on_hand(db: AsyncSession) -> dict:
    q = (
        select(Item.sku, Item.name, func.coalesce(func.sum(StockLevel.quantity), ZERO))
        .outerjoin(StockLevel, StockLevel.item_id == Item.id)
        .group_by(Item.sku, Item.name)
        .order_by(Item.name)
        .limit(1000)
    )
    rows = [{"sku": s, "item": n, "qty": _f(qty)} for s, n, qty in (await db.execute(q)).all()]
    return _table(
        "المخزون الحالي",
        [("sku", "الكود", "text"), ("item", "الصنف", "text"), ("qty", "الكمية", "number")],
        rows,
        {"عدد الأصناف": len(rows), "إجمالي الكميات": round(sum(r["qty"] for r in rows), 2)},
        "مستويات المخزون الحالية",
    )


async def get_payroll_summary(db: AsyncSession, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to)
    q = (
        select(Employee.first_name, Employee.last_name, Payslip.period_start, Payslip.period_end, Payslip.basic_wage, Payslip.allowances, Payslip.deductions, Payslip.net_pay, Payslip.status)
        .join(Employee, Employee.id == Payslip.employee_id)
        .where(Payslip.status.in_([PayslipStatus.APPROVED, PayslipStatus.PAID]), Payslip.period_end >= start, Payslip.period_start <= end)
        .order_by(Payslip.period_start, Employee.first_name)
    )
    rows = [
        {"employee": f"{a} {b}", "period": f"{ps.isoformat()} → {pe.isoformat()}", "basic": _f(bw), "allowances": _f(al), "deductions": _f(de), "net": _f(net), "status": st.value}
        for a, b, ps, pe, bw, al, de, net, st in (await db.execute(q)).all()
    ]
    return _table(
        "ملخص الرواتب",
        [("employee", "الموظف", "text"), ("period", "الفترة", "text"), ("basic", "الأساسي", "money"), ("allowances", "البدلات", "money"), ("deductions", "الاستقطاعات", "money"), ("net", "الصافي", "money"), ("status", "الحالة", "text")],
        rows,
        {"إجمالي الأساسي": round(sum(r["basic"] for r in rows), 2), "إجمالي البدلات": round(sum(r["allowances"] for r in rows), 2), "إجمالي الاستقطاعات": round(sum(r["deductions"] for r in rows), 2), "صافي الرواتب": round(sum(r["net"] for r in rows), 2), "عدد القسائم": len(rows)},
        "قسائم رواتب معتمدة/مدفوعة",
        (start, end),
    )


async def get_expenses_by_account(db: AsyncSession, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to)
    names = await _names(db)
    rows, total = [], ZERO
    for code, dr, cr in await _ledger(db, start, end, prefix="5"):
        amt = dr - cr
        total += amt
        rows.append({"code": code, "account": names.get(code, code), "amount": _f(amt)})
    for r in rows:
        r["share"] = round(r["amount"] / float(total) * 100, 1) if total else 0
    return _table(
        "المصروفات حسب الحساب",
        [("code", "الكود", "text"), ("account", "الحساب", "text"), ("amount", "المبلغ", "money"), ("share", "النسبة %", "percent")],
        rows,
        {"إجمالي المصروفات": _f(total)},
        "قيود مرحّلة — حسابات 5xxx",
        (start, end),
    )


# ── registry fragment (merged into REPORT_REGISTRY by service.py) ────────────

_DATES = {
    "date_from": {"type": "string", "description": "بداية الفترة بصيغة YYYY-MM-DD (افتراضي: أول الشهر الحالي)"},
    "date_to": {"type": "string", "description": "نهاية الفترة بصيغة YYYY-MM-DD (افتراضي: اليوم)"},
}
_LIMIT = {"limit": {"type": "integer", "description": "أقصى عدد صفوف"}}


def _p(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


EXTRA_REPORTS: dict[str, dict[str, Any]] = {
    "get_profit_and_loss": {"fn": get_profit_and_loss, "description": "قائمة الدخل: الإيرادات وتكلفة المبيعات ومجمل الربح والمصروفات وصافي الربح وهامش الربح لفترة محددة.", "parameters": _p(_DATES)},
    "get_balance_sheet": {"fn": get_balance_sheet, "description": "الميزانية العمومية في تاريخ معين: الأصول والخصوم وحقوق الملكية.", "parameters": _p({"as_of": {"type": "string", "description": "تاريخ المركز المالي YYYY-MM-DD (افتراضي: اليوم)"}})},
    "get_trial_balance_report": {"fn": get_trial_balance_report, "description": "ميزان المراجعة بكل الحسابات (مدين/دائن/رصيد) لفترة محددة.", "parameters": _p(_DATES)},
    "get_vat_summary": {"fn": get_vat_summary, "description": "ملخص ضريبة القيمة المضافة المحصّلة والمستحقة للسداد لفترة محددة.", "parameters": _p(_DATES)},
    "get_cash_flow": {"fn": get_cash_flow, "description": "التدفقات النقدية الشهرية: المقبوضات والمدفوعات وصافي التدفق ورصيد النقدية.", "parameters": _p(_DATES)},
    "get_account_ledger": {"fn": get_account_ledger, "description": "كشف حساب تفصيلي لحساب محاسبي معيّن (مثل 1100 النقدية أو 1200 العملاء) بالحركات والرصيد الجاري.", "parameters": _p({"account_code": {"type": "string", "description": "كود الحساب مثل 1100"}, **_DATES}, ["account_code"])},
    "get_ar_aging": {"fn": get_ar_aging, "description": "أعمار الديون: الفواتير غير المسددة مقسمة حسب مدة التأخر (30/60/90 يوم) مع إجمالي كل فئة.", "parameters": _p({})},
    "get_sales_by_customer": {"fn": get_sales_by_customer, "description": "إجمالي المبيعات وعدد الفواتير لكل عميل في فترة محددة.", "parameters": _p({**_DATES, **_LIMIT})},
    "get_top_selling_items": {"fn": get_top_selling_items, "description": "الأصناف الأكثر مبيعًا (كمية وإيراد) في فترة محددة.", "parameters": _p({**_DATES, **_LIMIT})},
    "get_daily_sales": {"fn": get_daily_sales, "description": "المبيعات اليومية (عدد الفواتير، قبل الضريبة، الضريبة، الإجمالي) في فترة محددة.", "parameters": _p(_DATES)},
    "get_customer_statement": {"fn": get_customer_statement, "description": "كشف حساب عميل بالاسم: فواتيره وحالتها والمستحق عليه.", "parameters": _p({"customer_name": {"type": "string", "description": "اسم العميل أو جزء منه"}, **_DATES}, ["customer_name"])},
    "get_cheques_due": {"fn": get_cheques_due, "description": "الشيكات الواردة والصادرة المستحقة أو المتأخرة خلال عدد أيام قادمة.", "parameters": _p({"days": {"type": "integer", "description": "عدد الأيام القادمة (افتراضي 30)"}})},
    "get_low_stock": {"fn": get_low_stock, "description": "الأصناف التي نفد مخزونها أو أقل من حد معين.", "parameters": _p({"threshold": {"type": "integer", "description": "الحد الأدنى للكمية (افتراضي 5)"}})},
    "get_stock_on_hand": {"fn": get_stock_on_hand, "description": "الكمية المتاحة حاليًا لكل صنف في المخزون.", "parameters": _p({})},
    "get_payroll_summary": {"fn": get_payroll_summary, "description": "ملخص الرواتب المعتمدة/المدفوعة: الأساسي والبدلات والاستقطاعات والصافي لكل موظف.", "parameters": _p(_DATES)},
    "get_expenses_by_account": {"fn": get_expenses_by_account, "description": "توزيع المصروفات حسب الحساب مع نسبة كل بند لفترة محددة.", "parameters": _p(_DATES)},
}
