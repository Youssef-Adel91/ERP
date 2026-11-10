"""
app/modules/reporting/more_reports.py — Phase D reports (payables, inventory value, daily brief)

Same contract as extra_reports.py (standard table shape, read-only, numbers
come from operational tables / posted ledger — never from the model).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.models import Contact
from app.modules.inventory.models.core import CostLayer, Item
from app.modules.purchasing.models.billing import VendorBill, VendorBillStatus
from app.modules.purchasing.models.payments import PaymentAllocation, SupplierPayment, SupplierPaymentStatus
from app.modules.reporting.extra_reports import (
    _BUCKETS,
    ZERO,
    _contact_names,
    _ar_norm_py,
    _ar_norm_sql,
    _f,
    _ledger,
    _p,
    _period,
    _table,
    get_ar_aging,
    get_cheques_due,
    get_low_stock,
)
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus


async def _bill_outstanding(db: AsyncSession, bills: list[VendorBill]) -> dict:
    """bill_id → amount already paid (posted supplier payments only)."""
    if not bills:
        return {}
    q = (
        select(PaymentAllocation.bill_id, func.coalesce(func.sum(PaymentAllocation.allocated_amount), ZERO))
        .join(SupplierPayment, SupplierPayment.id == PaymentAllocation.payment_id)
        .where(SupplierPayment.status == SupplierPaymentStatus.POSTED, PaymentAllocation.bill_id.in_([b.id for b in bills]))
        .group_by(PaymentAllocation.bill_id)
    )
    return {bid: paid for bid, paid in (await db.execute(q)).all()}


async def get_ap_aging(db: AsyncSession) -> dict:
    today = date.today()
    bills = (await db.execute(select(VendorBill).where(VendorBill.status == VendorBillStatus.POSTED).order_by(VendorBill.due_date))).scalars().all()
    paid = await _bill_outstanding(db, bills)
    names = await _contact_names(db, {b.supplier_id for b in bills})
    totals = {b[0]: ZERO for b in _BUCKETS}
    rows = []
    for b in bills:
        due = b.total_amount - paid.get(b.id, ZERO)
        if due <= 0:
            continue
        late = (today - b.due_date).days
        label = _BUCKETS[0][0] if late <= 0 else next(x[0] for x in _BUCKETS[1:] if x[1] <= late <= x[2])
        totals[label] += due
        rows.append({"bill": b.bill_number, "supplier": names.get(b.supplier_id, "غير معروف"), "due_date": b.due_date.isoformat(), "days_late": max(late, 0), "bucket": label, "amount": _f(due)})
    summary = {k: _f(v) for k, v in totals.items()}
    summary["إجمالي المستحق للموردين"] = _f(sum(totals.values(), ZERO))
    return _table(
        "أعمار الدائنين (الموردون)",
        [("bill", "الفاتورة", "text"), ("supplier", "المورد", "text"), ("due_date", "الاستحقاق", "date"), ("days_late", "أيام التأخير", "number"), ("bucket", "الفئة", "text"), ("amount", "المتبقي", "money")],
        rows,
        summary,
        "فواتير الموردين المرحّلة مخصومًا منها المدفوعات",
    )


async def get_purchases_by_supplier(db: AsyncSession, date_from: str | None = None, date_to: str | None = None, limit: int = 20) -> dict:
    start, end = _period(date_from, date_to)
    q = (
        select(VendorBill.supplier_id, func.count(VendorBill.id), func.coalesce(func.sum(VendorBill.total_amount), ZERO))
        .where(VendorBill.status == VendorBillStatus.POSTED, VendorBill.bill_date.between(start, end))
        .group_by(VendorBill.supplier_id)
        .order_by(func.sum(VendorBill.total_amount).desc())
        .limit(max(1, min(limit, 200)))
    )
    data = (await db.execute(q)).all()
    names = await _contact_names(db, {r[0] for r in data})
    rows = [{"supplier": names.get(s, "غير معروف"), "bills": int(n), "total": _f(t)} for s, n, t in data]
    return _table(
        "المشتريات حسب المورد",
        [("supplier", "المورد", "text"), ("bills", "عدد الفواتير", "number"), ("total", "إجمالي المشتريات", "money")],
        rows,
        {"إجمالي المشتريات": round(sum(r["total"] for r in rows), 2), "عدد الموردين": len(rows)},
        "فواتير الموردين المرحّلة",
        (start, end),
    )


async def get_supplier_statement(db: AsyncSession, supplier_name: str, date_from: str | None = None, date_to: str | None = None) -> dict:
    start, end = _period(date_from, date_to)
    if not date_from:
        start = date(2000, 1, 1)
    s = (await db.execute(select(Contact).where(_ar_norm_sql(Contact.name).like(f"%{_ar_norm_py(supplier_name)}%")).limit(1))).scalar_one_or_none()
    if s is None:
        return _table("كشف حساب مورد", [("note", "ملاحظة", "text")], [{"note": f"لا يوجد مورد باسم «{supplier_name}»"}], {}, "جهات الاتصال")
    bills = (
        await db.execute(
            select(VendorBill).where(VendorBill.supplier_id == s.id, VendorBill.status != VendorBillStatus.CANCELLED, VendorBill.bill_date.between(start, end)).order_by(VendorBill.bill_date)
        )
    ).scalars().all()
    paid = await _bill_outstanding(db, bills)
    rows = []
    for b in bills:
        p = paid.get(b.id, ZERO)
        rows.append({"date": b.bill_date.isoformat(), "bill": b.bill_number, "status": getattr(b.status, "value", b.status), "total": _f(b.total_amount), "paid": _f(p), "remaining": _f(b.total_amount - p)})
    posted = [b for b in bills if b.status == VendorBillStatus.POSTED]
    remaining = sum((b.total_amount - paid.get(b.id, ZERO) for b in posted), ZERO)
    return _table(
        f"كشف حساب المورد: {s.name}",
        [("date", "التاريخ", "date"), ("bill", "الفاتورة", "text"), ("status", "الحالة", "text"), ("total", "الإجمالي", "money"), ("paid", "المدفوع", "money"), ("remaining", "المتبقي", "money")],
        rows,
        {"المورد": s.name, "إجمالي الفواتير": _f(sum((b.total_amount for b in bills), ZERO)), "المتبقي للمورد": _f(remaining), "عدد الفواتير": len(bills)},
        "فواتير المورد ومدفوعاته",
        (start, end),
    )


async def get_inventory_valuation(db: AsyncSession) -> dict:
    """Stock value from open FIFO/weighted cost layers (qty_remaining × current unit cost)."""
    q = (
        select(Item.sku, Item.name, func.sum(CostLayer.qty_remaining), func.sum(CostLayer.qty_remaining * CostLayer.unit_cost_current))
        .join(Item, Item.id == CostLayer.item_id)
        .where(CostLayer.qty_remaining > 0)
        .group_by(Item.sku, Item.name)
        .order_by(func.sum(CostLayer.qty_remaining * CostLayer.unit_cost_current).desc())
    )
    rows = []
    for sku, name, qty, value in (await db.execute(q)).all():
        qty_d, val_d = Decimal(qty or 0), Decimal(value or 0)
        rows.append({"sku": sku, "item": name, "qty": _f(qty_d), "avg_cost": _f(val_d / qty_d) if qty_d else 0.0, "value": _f(val_d)})
    return _table(
        "تقييم المخزون",
        [("sku", "الكود", "text"), ("item", "الصنف", "text"), ("qty", "الكمية", "number"), ("avg_cost", "متوسط التكلفة", "money"), ("value", "القيمة", "money")],
        rows,
        {"إجمالي قيمة المخزون": round(sum(r["value"] for r in rows), 2), "عدد الأصناف": len(rows)},
        "طبقات التكلفة المفتوحة (الكمية المتبقية × التكلفة الحالية)",
    )


async def get_daily_brief(db: AsyncSession, day: str | None = None) -> dict:
    """One-screen morning brief: today's sales, cash, receivables, cheques, stock alerts."""
    try:
        d = date.fromisoformat(day[:10]) if day else date.today()
    except ValueError:
        d = date.today()
    sales = (
        await db.execute(
            select(func.count(SalesInvoice.id), func.coalesce(func.sum(SalesInvoice.grand_total), ZERO)).where(
                SalesInvoice.status.in_([SalesInvoiceStatus.POSTED, SalesInvoiceStatus.PAID]), SalesInvoice.issue_date == d
            )
        )
    ).one()
    cash_rows = await _ledger(db, None, d, code="1100")
    cash = sum((dr - cr for _, dr, cr in cash_rows), ZERO)
    ar = (await get_ar_aging(db))["summary"]
    ap = (await get_ap_aging(db))["summary"]
    cheques = await get_cheques_due(db, 7)
    low = await get_low_stock(db, 5)
    metrics = [
        ("صافي مبيعات اليوم (بعد المرتجعات)", _f(sales[1]), "money"),
        ("عدد فواتير اليوم", int(sales[0]), "number"),
        ("رصيد النقدية", _f(cash), "money"),
        ("إجمالي مستحق من العملاء", ar.get("الإجمالي المستحق", 0), "money"),
        ("إجمالي مستحق للموردين", ap.get("إجمالي المستحق للموردين", 0), "money"),
        ("شيكات مستحقة خلال 7 أيام", cheques.get("count", 0), "number"),
        ("أصناف منخفضة المخزون", low.get("count", 0), "number"),
    ]
    rows = [{"metric": m, "value": v} for m, v, _ in metrics]
    return _table(
        f"الملخص اليومي — {d.isoformat()}",
        [("metric", "المؤشر", "text"), ("value", "القيمة", "number")],
        rows,
        {m: v for m, v, _ in metrics},
        "المبيعات والدفتر والذمم والشيكات والمخزون",
        (d, d),
    )


MORE_REPORTS: dict[str, dict[str, Any]] = {
    "get_ap_aging": {"fn": get_ap_aging, "description": "أعمار الدائنين: فواتير الموردين غير المسددة مقسمة حسب مدة التأخر مع إجمالي كل فئة.", "parameters": _p({})},
    "get_purchases_by_supplier": {"fn": get_purchases_by_supplier, "description": "إجمالي المشتريات وعدد الفواتير لكل مورد في فترة محددة.", "parameters": _p({"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string", "description": "YYYY-MM-DD"}, "limit": {"type": "integer", "description": "أقصى عدد صفوف"}})},
    "get_supplier_statement": {"fn": get_supplier_statement, "description": "كشف حساب مورد بالاسم: فواتيره والمدفوع والمتبقي.", "parameters": _p({"supplier_name": {"type": "string", "description": "اسم المورد أو جزء منه"}, "date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string", "description": "YYYY-MM-DD"}}, ["supplier_name"])},
    "get_inventory_valuation": {"fn": get_inventory_valuation, "description": "تقييم المخزون: قيمة كل صنف (الكمية × متوسط التكلفة) وإجمالي قيمة المخزون.", "parameters": _p({})},
    "get_daily_brief": {"fn": get_daily_brief, "description": "الملخص اليومي: مبيعات اليوم، النقدية، المستحق من العملاء وللموردين، الشيكات القريبة، والمخزون المنخفض.", "parameters": _p({"day": {"type": "string", "description": "اليوم YYYY-MM-DD (افتراضي: اليوم)"}})},
}
