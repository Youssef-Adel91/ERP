"""
app/modules/reporting/tabular.py — one table shape + Excel/CSV export for EVERY report

Any report result (new catalogue reports already return the standard shape;
legacy ones return ad-hoc dicts) is normalised to:

    {"title", "period", "summary", "columns", "rows", "source"}

so the chat UI can render it generically and the user can download it as
.xlsx / .csv with a single click. Exporters are pure functions (no DB).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

_LABELS = {
    "invoice_number": "رقم الفاتورة", "customer_name": "العميل", "due_date": "الاستحقاق", "days_overdue": "أيام التأخير",
    "grand_total_egp": "الإجمالي", "currency": "العملة", "name": "الاسم", "month": "الشهر", "revenue_egp": "الإيراد",
    "total_egp": "الإجمالي", "total_revenue_egp": "إجمالي الإيرادات", "total_receivables_egp": "المستحق من العملاء",
    "total_payables_egp": "المستحق للموردين", "cash_balance_egp": "الرصيد النقدي", "account_name": "الحساب",
    "account_code": "الكود", "amount_egp": "المبلغ", "count": "العدد",
}


def _label(key: str) -> str:
    return _LABELS.get(key, key.replace("_", " "))


def _col_type(key: str, sample: Any) -> str:
    k = key.lower()
    if isinstance(sample, bool):
        return "text"
    if isinstance(sample, (int, float)):
        if k.endswith("_pct") or "percent" in k:
            return "percent"
        if "egp" in k or "amount" in k or "total" in k or "revenue" in k or "balance" in k:
            return "money"
        return "number"
    if "date" in k:
        return "date"
    return "text"


def normalize(name: str, result: dict[str, Any], title: str | None = None) -> dict[str, Any]:
    """Return the standard table shape for any report result."""
    if isinstance(result, dict) and "columns" in result and "rows" in result:
        return result
    summary: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for k, v in result.items():
        if k == "source":
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict) and not rows:
            rows = v
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            summary[_label(k)] = v
    if not rows:
        # fall back to a 2-column key/value table so something is always downloadable
        rows = [{"item": k, "value": v} for k, v in summary.items()]
        columns = [{"key": "item", "label": "البند", "type": "text"}, {"key": "value", "label": "القيمة", "type": "money"}]
        summary = {}
    else:
        flat = [{k: v for k, v in r.items() if not isinstance(v, (dict, list))} for r in rows]
        rows = flat
        columns = [{"key": k, "label": _label(k), "type": _col_type(k, rows[0][k])} for k in rows[0]]
    return {
        "title": title or name,
        "period": None,
        "summary": summary,
        "columns": columns,
        "rows": rows,
        "count": len(rows),
        "source": result.get("source", ""),
    }


# ── exporters ────────────────────────────────────────────────────────────────


def to_csv(table: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([table["title"]])
    for k, v in (table.get("summary") or {}).items():
        w.writerow([k, v])
    w.writerow([])
    cols = table["columns"]
    w.writerow([c["label"] for c in cols])
    for r in table["rows"]:
        w.writerow([r.get(c["key"], "") for c in cols])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel reads Arabic correctly


def to_xlsx(table: dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = (table["title"] or "تقرير")[:30].replace("/", "-").replace("\\", "-").replace("?", "").replace("*", "").replace("[", "").replace("]", "").replace(":", "")
    ws.sheet_view.rightToLeft = True
    right = Alignment(horizontal="right", vertical="center")

    ws.append([table["title"]])
    ws["A1"].font = Font(bold=True, size=14)
    p = table.get("period")
    ws.append([f"الفترة: {p['from']} → {p['to']}" if p else f"تاريخ الإصدار: {datetime.now():%Y-%m-%d %H:%M}"])
    ws.append([])
    for k, v in (table.get("summary") or {}).items():
        ws.append([k, v])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        if isinstance(v, (int, float)):
            ws.cell(row=ws.max_row, column=2).number_format = "#,##0.00"
    ws.append([])

    cols = table["columns"]
    header_row = ws.max_row + 1
    ws.append([c["label"] for c in cols])
    fill = PatternFill("solid", fgColor="1F3A5F")
    for i in range(1, len(cols) + 1):
        cell = ws.cell(row=header_row, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r in table["rows"]:
        ws.append([r.get(c["key"], "") for c in cols])
        for i, c in enumerate(cols, start=1):
            cell = ws.cell(row=ws.max_row, column=i)
            cell.alignment = right
            if c["type"] == "money":
                cell.number_format = "#,##0.00"
            elif c["type"] == "percent":
                cell.number_format = '0.0"%"'
            elif c["type"] == "number":
                cell.number_format = "#,##0.##"

    if cols:
        ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    for i in range(1, max(len(cols), 2) + 1):
        width = max(
            [len(str(ws.cell(row=r, column=i).value or "")) for r in range(1, min(ws.max_row, 200) + 1)] + [10]
        )
        ws.column_dimensions[get_column_letter(i)].width = min(width + 3, 50)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
