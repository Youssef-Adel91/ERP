"""Pure unit tests for Phase D: scheduling helpers + routing/meta of the new reports."""
from datetime import date

import pytest

from app.modules.reporting.catalog import REPORT_META, can_run, route_question
from app.modules.reporting.schedules import _advance, resolve_period, validate_spec
from app.modules.reporting.service import REPORT_REGISTRY

NEW = ["get_ap_aging", "get_purchases_by_supplier", "get_supplier_statement", "get_inventory_valuation", "get_daily_brief"]


@pytest.mark.parametrize("name", NEW)
def test_new_reports_registered_and_described(name):
    assert name in REPORT_REGISTRY and name in REPORT_META
    assert REPORT_REGISTRY[name]["description"]
    assert REPORT_META[name]["roles"]


@pytest.mark.parametrize(
    "question,report",
    [
        ("أعمار الدائنين", "get_ap_aging"),
        ("ديون الموردين", "get_ap_aging"),
        ("تقييم المخزون", "get_inventory_valuation"),
        ("قيمة المخزون", "get_inventory_valuation"),
        ("المشتريات حسب المورد", "get_purchases_by_supplier"),
        ("الملخص اليومي", "get_daily_brief"),
        ("أعمار الديون", "get_ar_aging"),
    ],
)
def test_new_routes(question, report):
    routed = route_question(question)
    assert routed is not None and routed[0] == report


def test_supplier_statement_route():
    name, params = route_question("كشف حساب المورد النور")
    assert name == "get_supplier_statement"
    assert "نور" in params["supplier_name"]


def test_customer_statement_still_works():
    name, params = route_question("كشف حساب العميل أحمد")
    assert name == "get_customer_statement" and params["customer_name"] == "احمد"


def test_payables_are_finance_only():
    assert can_run("get_ap_aging", ["ACCOUNTING"])
    assert not can_run("get_ap_aging", ["STAFF"])
    assert not can_run("get_ap_aging", ["SALES"])
    assert not can_run("get_inventory_valuation", ["STAFF"])  # cost data


def test_resolve_period():
    today = date(2026, 11, 14)
    assert resolve_period("yesterday", today) == {"date_from": "2026-11-13", "date_to": "2026-11-13"}
    assert resolve_period("last_7_days", today) == {"date_from": "2026-11-08", "date_to": "2026-11-14"}
    assert resolve_period("month_to_date", today) == {"date_from": "2026-11-01", "date_to": "2026-11-14"}
    assert resolve_period("last_month", today) == {"date_from": "2026-10-01", "date_to": "2026-10-31"}
    assert resolve_period("none", today) == {}


def test_advance():
    assert _advance("daily", date(2026, 11, 14)) == date(2026, 11, 15)
    assert _advance("weekly", date(2026, 11, 14)) == date(2026, 11, 21)
    assert _advance("monthly", date(2026, 11, 14)) == date(2026, 12, 14)
    assert _advance("monthly", date(2026, 12, 31)) == date(2027, 1, 28)  # clamped, never invalid


def test_validate_spec():
    ok = validate_spec("get_ar_aging", "weekly", "none", "xlsx", ["a@b.com"])
    assert ok is None
    assert validate_spec("nope", "weekly", "none", "xlsx", ["a@b.com"])
    assert validate_spec("get_ar_aging", "hourly", "none", "xlsx", ["a@b.com"])
    assert validate_spec("get_ar_aging", "weekly", "forever", "xlsx", ["a@b.com"])
    assert validate_spec("get_ar_aging", "weekly", "none", "pdf", ["a@b.com"])
    assert validate_spec("get_ar_aging", "weekly", "none", "xlsx", [])
    assert validate_spec("get_ar_aging", "weekly", "none", "xlsx", ["not-an-email"])
    assert validate_spec("get_ar_aging", "weekly", "none", "xlsx", [f"u{i}@b.com" for i in range(6)])
