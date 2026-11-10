"""
app/modules/reporting/catalog.py — report metadata, role access and the rule-based intent router

1. REPORT_META: Arabic title, category and which roles may run each report.
   Financial statements are OWNER/ADMIN/ACCOUNTING only; sales reports also
   allow SALES; stock reports also allow STAFF. The AI assistant, the report
   catalogue and the export endpoint ALL go through `can_run` — an LLM can
   never be used to read a report the caller's role could not open directly.

2. route_question(): a deterministic Arabic/English intent router. It is the
   engine behind the assistant when no AI model key is configured ("ready
   except the model hookup"), and a safety net when the model is down. When a
   model IS configured, the model picks the report (function-calling) and this
   router is not used.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

FIN = {"OWNER", "ADMIN", "ACCOUNTING"}
SALES = FIN | {"SALES"}
STOCK = FIN | {"STAFF", "SALES"}

REPORT_META: dict[str, dict[str, Any]] = {
    "get_financial_summary": {"title": "الملخص المالي", "category": "مالية", "roles": FIN},
    "get_profit_and_loss": {"title": "قائمة الدخل (الأرباح والخسائر)", "category": "مالية", "roles": FIN},
    "get_balance_sheet": {"title": "الميزانية العمومية", "category": "مالية", "roles": FIN},
    "get_trial_balance_report": {"title": "ميزان المراجعة", "category": "مالية", "roles": FIN},
    "get_vat_summary": {"title": "ملخص ضريبة القيمة المضافة", "category": "مالية", "roles": FIN},
    "get_cash_flow": {"title": "التدفقات النقدية", "category": "مالية", "roles": FIN},
    "get_account_ledger": {"title": "كشف حساب محاسبي", "category": "مالية", "roles": FIN},
    "get_expenses_by_account": {"title": "المصروفات حسب الحساب", "category": "مالية", "roles": FIN},
    "get_expense_breakdown": {"title": "توزيع مصروفات الشهر", "category": "مالية", "roles": FIN},
    "get_revenue_trend": {"title": "اتجاه الإيرادات", "category": "مالية", "roles": FIN},
    "get_revenue_variance_analysis": {"title": "تحليل تغيّر الإيرادات", "category": "مالية", "roles": FIN},
    "get_cheques_due": {"title": "الشيكات المستحقة", "category": "مالية", "roles": FIN},
    "get_ar_aging": {"title": "أعمار الديون", "category": "مبيعات", "roles": SALES},
    "get_overdue_invoices": {"title": "الفواتير المتأخرة", "category": "مبيعات", "roles": SALES},
    "get_top_customers_by_revenue": {"title": "أكبر العملاء", "category": "مبيعات", "roles": SALES},
    "get_sales_by_customer": {"title": "المبيعات حسب العميل", "category": "مبيعات", "roles": SALES},
    "get_top_selling_items": {"title": "الأصناف الأكثر مبيعًا", "category": "مبيعات", "roles": SALES},
    "get_daily_sales": {"title": "المبيعات اليومية", "category": "مبيعات", "roles": SALES},
    "get_sales_this_month_vs_last": {"title": "المبيعات: هذا الشهر مقابل الماضي", "category": "مبيعات", "roles": SALES},
    "get_customer_statement": {"title": "كشف حساب عميل", "category": "مبيعات", "roles": SALES},
    "get_customer_trust_profile": {"title": "تقييم ثقة عميل", "category": "مبيعات", "roles": SALES},
    "get_low_stock": {"title": "المخزون المنخفض", "category": "مخزون", "roles": STOCK},
    "get_stock_on_hand": {"title": "المخزون الحالي", "category": "مخزون", "roles": STOCK},
    "get_ap_aging": {"title": "أعمار الدائنين (الموردون)", "category": "مشتريات", "roles": FIN},
    "get_purchases_by_supplier": {"title": "المشتريات حسب المورد", "category": "مشتريات", "roles": FIN},
    "get_supplier_statement": {"title": "كشف حساب مورد", "category": "مشتريات", "roles": FIN},
    "get_inventory_valuation": {"title": "تقييم المخزون", "category": "مخزون", "roles": FIN},
    "get_daily_brief": {"title": "الملخص اليومي", "category": "مالية", "roles": FIN},
    "get_payroll_summary": {"title": "ملخص الرواتب", "category": "موارد بشرية", "roles": FIN},
}


def can_run(name: str, roles: list[str] | set[str] | None) -> bool:
    """roles=None means a trusted internal caller (e.g. the owner's own WhatsApp)."""
    if roles is None:
        return True
    meta = REPORT_META.get(name)
    return bool(meta and set(roles) & meta["roles"])


# ── text normalisation ───────────────────────────────────────────────────────

_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})
_DIAC = re.compile(r"[ً-ْـ]")


def norm(text: str) -> str:
    return _DIAC.sub("", text).translate(_AR_MAP).lower().strip()


_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7, "اغسطس": 8,
    "سبتمبر": 9, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12, "january": 1, "february": 2, "march": 3,
    "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _month_range(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    nxt = date(y + (m == 12), (m % 12) + 1, 1)
    return start, nxt - timedelta(days=1)


def parse_period(q: str, today: date | None = None) -> tuple[str, str] | None:
    """Pull a date window out of a question; None means 'use the report default'."""
    t = norm(q)
    today = today or date.today()
    iso = re.findall(r"\d{4}-\d{2}-\d{2}", t)
    if len(iso) >= 2:
        return iso[0], iso[1]
    if len(iso) == 1:
        return iso[0], iso[0]
    if re.search(r"امبارح|امس|yesterday", t):
        d = today - timedelta(days=1)
        return d.isoformat(), d.isoformat()
    if re.search(r"النهارده|النهاردا|اليوم|today", t):
        return today.isoformat(), today.isoformat()
    m = re.search(r"(?:اخر|آخر|اخر|last)\s*(\d+)\s*(يوم|ايام|اسبوع|اسابيع|شهر|شهور|اشهر|days?|weeks?|months?)", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * (30 if unit.startswith(("شهر", "شهور", "اشهر", "month")) else 7 if unit.startswith(("اسبوع", "اسابيع", "week")) else 1)
        return (today - timedelta(days=days)).isoformat(), today.isoformat()
    if re.search(r"الاسبوع (اللي|الي) فات|الاسبوع الماضي|last week", t):
        end = today - timedelta(days=today.weekday() + 1)
        return (end - timedelta(days=6)).isoformat(), end.isoformat()
    if re.search(r"(هذا|هذه|ده|دي|الحالي|الحاليه|this) ?(الاسبوع|week)|الاسبوع ده", t):
        return (today - timedelta(days=today.weekday())).isoformat(), today.isoformat()
    if re.search(r"الشهر (اللي|الي) فات|الشهر الماضي|الشهر السابق|last month", t):
        s, e = _month_range(today.year - (today.month == 1), 12 if today.month == 1 else today.month - 1)
        return s.isoformat(), e.isoformat()
    if re.search(r"السنه (اللي|الي) فاتت|العام الماضي|السنه الماضيه|last year", t):
        return date(today.year - 1, 1, 1).isoformat(), date(today.year - 1, 12, 31).isoformat()
    if re.search(r"السنه|العام|سنوي|this year|ytd", t):
        return date(today.year, 1, 1).isoformat(), today.isoformat()
    if re.search(r"الربع|quarter", t):
        qs = (today.month - 1) // 3 * 3 + 1
        return date(today.year, qs, 1).isoformat(), today.isoformat()
    for name, num in _MONTHS.items():
        if name in t:
            ym = re.search(r"(20\d{2})", t)
            y = int(ym.group(1)) if ym else today.year
            s, e = _month_range(y, num)
            return s.isoformat(), e.isoformat()
    if re.search(r"الشهر|شهر|this month|month", t):
        return today.replace(day=1).isoformat(), today.isoformat()
    return None


# ── intent rules (first strong match wins; order = specificity) ──────────────

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("get_daily_brief", ("ملخص اليوم", "ملخص يومي", "الملخص اليومي", "موجز اليوم", "daily brief", "morning brief")),
    ("get_trial_balance_report", ("ميزان المراجعه", "trial balance")),
    ("get_ap_aging", ("اعمار الدائنين", "اعمار الموردين", "ديون الموردين", "مستحق للموردين", "مستحقات الموردين", "ap aging", "payables aging")),
    ("get_inventory_valuation", ("تقييم المخزون", "قيمه المخزون", "قيمة المخزون", "inventory valuation", "stock value")),
    ("get_purchases_by_supplier", ("مشتريات كل مورد", "المشتريات حسب المورد", "مشتريات حسب المورد", "purchases by supplier", "اكبر الموردين")),
    ("get_balance_sheet", ("ميزانيه", "المركز المالي", "balance sheet")),
    ("get_profit_and_loss", ("قائمه الدخل", "صافي الربح", "صافي ربح", "ارباح", "ربح", "خسائر", "خساره", "profit", "p&l", "income statement", "margin", "هامش")),
    ("get_vat_summary", ("ضريبه", "ضرايب", "القيمه المضافه", "vat", "tax")),
    ("get_cash_flow", ("التدفق", "تدفق", "cash flow", "cashflow", "السيوله")),
    ("get_ar_aging", ("اعمار الديون", "اعمار", "aging", "ageing")),
    ("get_overdue_invoices", ("متاخر", "متأخر", "overdue", "late invoices")),
    ("get_cheques_due", ("شيكات", "شيك", "cheque", "check due")),
    ("get_low_stock", ("مخزون منخفض", "مخزونها منخفض", "مخزونه منخفض", "منخفض", "قليل", "ناقص", "نفد", "نفذ", "خلص", "قارب على النفاد", "low stock", "out of stock", "reorder")),
    ("get_stock_on_hand", ("المخزون", "مخزون", "stock", "inventory", "جرد")),
    ("get_payroll_summary", ("رواتب", "مرتبات", "مرتب", "payroll", "salary", "salaries")),
    ("get_expenses_by_account", ("مصروفات", "مصاريف", "expenses", "المصروف")),
    ("get_top_selling_items", ("الاكثر مبيعا", "اكتر صنف", "اكتر منتج", "افضل الاصناف", "افضل المنتجات", "اكثر منتج", "best selling", "top items", "top products")),
    ("get_sales_by_customer", ("مبيعات كل عميل", "المبيعات حسب العميل", "مبيعات حسب العميل", "اكبر 3 عملاء", "اكبر عملاء", "sales by customer")),
    ("get_top_customers_by_revenue", ("اكبر العملاء", "افضل العملاء", "اكتر عميل", "اهم العملاء", "top customers", "best customers", "top customers", "top 3 customers")),
    ("get_daily_sales", ("المبيعات اليوميه", "مبيعات يوميه", "مبيعات النهارده", "مبيعات اليوم", "daily sales", "المبيعات")),
    ("get_revenue_variance_analysis", ("ليه الايرادات", "سبب تغير", "why revenue", "اختلاف الايرادات")),
    ("get_revenue_trend", ("ترند", "اتجاه الايرادات", "trend", "تطور الايرادات")),
    ("get_financial_summary", ("ملخص", "ايراد", "مديونيات", "نقديه", "رصيد", "الخزنه", "summary", "revenue", "cash balance", "receivable", "payable")),
]

_SUGGESTIONS = [
    "اعرض قائمة الدخل هذا الشهر",
    "مين أكبر العملاء عندي؟",
    "أعمار الديون",
    "الأصناف الأكثر مبيعًا آخر 30 يوم",
    "الشيكات المستحقة خلال 14 يوم",
    "إيه الأصناف اللي مخزونها منخفض؟",
    "ملخص ضريبة القيمة المضافة هذا الشهر",
    "التدفقات النقدية آخر 3 شهور",
    "أعمار الدائنين",
    "تقييم المخزون",
    "الملخص اليومي",
]


def suggestions() -> list[str]:
    return list(_SUGGESTIONS)


def route_question(q: str, roles: list[str] | set[str] | None = None) -> tuple[str, dict[str, Any]] | None:
    """Map a free-text question to (report_name, params), or None if nothing matches."""
    t = norm(q)

    # "كشف حساب <4-digit code>" → ledger, "كشف حساب <name>" → customer statement
    if "كشف حساب" in t or "statement" in t or "ledger" in t:
        code = re.search(r"\b(\d{4})\b", t)
        if not code and re.search(r"(?:ال|ل)?مورد", t):
            sname = re.sub(r"كشف حساب|statement|ledger|\b(?:ال|ل)?مورد\b|\bof\b|\bfor\b", "", t).strip(" ؟?")
            sname = re.sub(r"(هذا|الشهر|السنه|اخر|\d+|يوم).*$", "", sname).strip()
            if sname:
                sp = parse_period(q)
                return "get_supplier_statement", {"supplier_name": sname, **({"date_from": sp[0], "date_to": sp[1]} if sp else {})}
        period = parse_period(q)
        params: dict[str, Any] = {}
        if period:
            params["date_from"], params["date_to"] = period
        if code:
            return "get_account_ledger", {"account_code": code.group(1), **params}
        name = re.sub(r"كشف حساب|statement|ledger|\b(?:ال|ل)?عميل\b|\bof\b|\bfor\b", "", t).strip(" ؟?")
        name = re.sub(r"(هذا|الشهر|السنه|اخر|\d+|يوم).*$", "", name).strip()
        if name:
            return "get_customer_statement", {"customer_name": name, **params}

    for report, words in _RULES:
        if any(norm(w) in t for w in words):
            if not can_run(report, roles):
                continue
            params = {}
            meta_params = _params_for(report)
            period = parse_period(q)
            if period and "date_from" in meta_params:
                params["date_from"], params["date_to"] = period
            if period and report == "get_balance_sheet":
                params["as_of"] = period[1]
            days = re.search(r"(\d+)\s*(?:يوم|ايام|days?)", t)
            if days and report == "get_cheques_due":
                params["days"] = int(days.group(1))
            lim = re.search(r"(?:اكبر|اعلى|افضل|top|اكتر)\s*(\d+)", t)
            if lim and "limit" in meta_params:
                params["limit"] = int(lim.group(1))
            thr = re.search(r"(?:اقل من|under|below|<)\s*(\d+)", t)
            if thr and report == "get_low_stock":
                params["threshold"] = int(thr.group(1))
            return report, params
    return None


def _params_for(report: str) -> set[str]:
    from app.modules.reporting.service import REPORT_REGISTRY

    spec = REPORT_REGISTRY.get(report)
    return set(spec["parameters"]["properties"]) if spec else set()


def fallback_answer(table: dict[str, Any]) -> str:
    """Deterministic Arabic answer built from the report's real numbers."""
    parts = [f"{table['title']}"]
    p = table.get("period")
    if p:
        parts[0] += f" (من {p['from']} إلى {p['to']})"
    parts[0] += ":"
    for k, v in list((table.get("summary") or {}).items())[:6]:
        parts.append(f"• {k}: {v:,.2f}" if isinstance(v, float) else f"• {k}: {v}")
    n = table.get("count", len(table.get("rows", [])))
    if n:
        parts.append(f"عدد الصفوف في التقرير: {n} — تقدر تنزّله Excel أو CSV من الأزرار تحت.")
    elif not table.get("summary"):
        parts.append("لا توجد بيانات في هذه الفترة.")
    return "\n".join(parts)
