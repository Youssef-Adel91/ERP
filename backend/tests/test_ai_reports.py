"""AI report catalogue: question routing, role access, table normalisation, Excel/CSV export.

Pure unit tests (no database) — the SQL itself is verified live against a ledger.
"""
import csv
import io
from datetime import date

import pytest
from openpyxl import load_workbook

from app.modules.reporting.catalog import (
    REPORT_META,
    can_run,
    fallback_answer,
    norm,
    parse_period,
    route_question,
)
from app.modules.reporting.service import REPORT_REGISTRY
from app.modules.reporting.tabular import normalize, to_csv, to_xlsx

TODAY = date(2026, 11, 10)


def test_every_report_has_meta_and_roles():
    missing = [n for n in REPORT_REGISTRY if n not in REPORT_META]
    assert not missing, f"reports without role metadata: {missing}"
    for name, meta in REPORT_META.items():
        assert meta["roles"], name


@pytest.mark.parametrize(
    "question,report",
    [
        ("اعرض قائمة الدخل هذا الشهر", "get_profit_and_loss"),
        ("ما هي أرباحي؟", "get_profit_and_loss"),
        ("الميزانية العمومية", "get_balance_sheet"),
        ("ميزان المراجعة", "get_trial_balance_report"),
        ("ملخص ضريبة القيمة المضافة", "get_vat_summary"),
        ("التدفقات النقدية آخر 3 شهور", "get_cash_flow"),
        ("أعمار الديون", "get_ar_aging"),
        ("فيه فواتير متأخرة؟", "get_overdue_invoices"),
        ("الشيكات المستحقة خلال 14 يوم", "get_cheques_due"),
        ("إيه الأصناف اللي مخزونها منخفض؟", "get_low_stock"),
        ("رواتب الشهر ده", "get_payroll_summary"),
        ("مصروفات السنة دي", "get_expenses_by_account"),
        ("الأصناف الأكثر مبيعًا آخر 30 يوم", "get_top_selling_items"),
        ("مين أكبر العملاء عندي؟", "get_top_customers_by_revenue"),
        ("كشف حساب 1100", "get_account_ledger"),
        ("كشف حساب العميل أحمد", "get_customer_statement"),
        ("top customers", "get_top_customers_by_revenue"),
        ("show me profit this year", "get_profit_and_loss"),
    ],
)
def test_route_question(question, report):
    routed = route_question(question)
    assert routed is not None and routed[0] == report


def test_route_extracts_params():
    name, params = route_question("الشيكات المستحقة خلال 14 يوم")
    assert params == {"days": 14}
    name, params = route_question("كشف حساب 1100")
    assert params["account_code"] == "1100"
    name, params = route_question("كشف حساب العميل أحمد")
    assert params["customer_name"] == "احمد"
    name, params = route_question("أكبر 3 عملاء")
    assert params.get("limit") == 3


def test_unrelated_question_is_not_routed():
    assert route_question("ايه الجو النهارده") is None


def test_router_respects_roles():
    assert route_question("ما هي أرباحي؟", roles=["STAFF"]) is None
    assert route_question("أعمار الديون", roles=["SALES"])[0] == "get_ar_aging"
    assert can_run("get_profit_and_loss", ["ACCOUNTING"])
    assert not can_run("get_profit_and_loss", ["SALES"])
    assert can_run("get_low_stock", ["STAFF"])
    assert can_run("get_profit_and_loss", None)  # trusted internal caller
    assert not can_run("does_not_exist", ["OWNER"])


@pytest.mark.parametrize(
    "q,expected",
    [
        ("النهارده", ("2026-11-10", "2026-11-10")),
        ("امبارح", ("2026-11-09", "2026-11-09")),
        ("الشهر اللي فات", ("2026-10-01", "2026-10-31")),
        ("آخر 30 يوم", ("2026-10-11", "2026-11-10")),
        ("السنة دي", ("2026-01-01", "2026-11-10")),
        ("السنة اللي فاتت", ("2025-01-01", "2025-12-31")),
        ("من 2026-01-01 الى 2026-03-31", ("2026-01-01", "2026-03-31")),
        ("في مارس", ("2026-03-01", "2026-03-31")),
        ("الشهر ده", ("2026-11-01", "2026-11-10")),
    ],
)
def test_parse_period(q, expected):
    assert parse_period(q, TODAY) == expected


def test_parse_period_january_rollover():
    assert parse_period("الشهر اللي فات", date(2026, 1, 15)) == ("2025-12-01", "2025-12-31")


def test_norm_unifies_arabic_forms():
    assert norm("أرباحي إلى آخر مُدّة") == norm("ارباحي الى اخر مدة")


STD = {
    "title": "اختبار",
    "period": {"from": "2026-11-01", "to": "2026-11-10"},
    "summary": {"الإجمالي": 1234.5},
    "columns": [{"key": "a", "label": "الاسم", "type": "text"}, {"key": "b", "label": "المبلغ", "type": "money"}],
    "rows": [{"a": "عميل", "b": 10.5}, {"a": "x", "b": 20}],
    "count": 2,
}


def test_normalize_passes_standard_shape_through():
    assert normalize("x", STD) is STD


def test_normalize_legacy_report():
    legacy = {
        "count": 1,
        "total_overdue_egp": 500.0,
        "invoices": [{"invoice_number": "INV-1", "customer_name": "أحمد", "grand_total_egp": 500.0, "days_overdue": 3}],
        "source": "sales_invoices",
    }
    t = normalize("get_overdue_invoices", legacy, "متأخرة")
    assert t["title"] == "متأخرة" and len(t["rows"]) == 1
    assert {c["key"] for c in t["columns"]} == {"invoice_number", "customer_name", "grand_total_egp", "days_overdue"}
    assert next(c for c in t["columns"] if c["key"] == "grand_total_egp")["type"] == "money"


def test_normalize_scalar_only_report_is_still_downloadable():
    t = normalize("get_financial_summary", {"total_revenue_egp": 100.0, "cash_balance_egp": 50.0, "source": "x"})
    assert t["rows"] and t["columns"][0]["key"] == "item"


def test_csv_export_has_bom_summary_header_and_rows():
    raw = to_csv(STD)
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert rows[0] == ["اختبار"]
    assert ["الاسم", "المبلغ"] in rows
    assert ["عميل", "10.5"] in rows


def test_xlsx_export_is_valid_rtl_workbook():
    wb = load_workbook(io.BytesIO(to_xlsx(STD)))
    ws = wb.active
    assert ws.sheet_view.rightToLeft is True
    values = [[c.value for c in r] for r in ws.iter_rows()]
    assert any(r[:2] == ["الاسم", "المبلغ"] for r in values)
    assert any(r[:2] == ["عميل", 10.5] for r in values)


def test_fallback_answer_lists_summary_and_download_hint():
    text = fallback_answer(STD)
    assert "اختبار" in text and "1,234.50" in text and "Excel" in text
