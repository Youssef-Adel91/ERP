"""
app/plugins/travel/services/financials.py — Travel Booking Margin Calculation Service

Computes buy/sell margins from a travel Case's structured data.
Produces a strictly typed CaseFinancials summary that the GL listener consumes.

DECOUPLING CONTRACT:
  ✅ Pure computation — no DB writes, no accounting imports
  ✅ Works entirely from Case.data (the JSONB payload)
  ✅ Returns typed Pydantic models, not raw dicts
  ❌ Never imports from app.modules.accounting
  ❌ Never writes JournalEntry rows directly
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, model_validator


# ── Typed Models ───────────────────────────────────────────────────────────────


class ServiceLine(BaseModel):
    """A single priced service (flight, hotel, transfer, etc.) within a booking."""

    service_type: str
    supplier_id: str | None = None
    supplier_name: str | None = None
    description: str | None = None
    buy_price: Decimal = Decimal("0")
    sell_price: Decimal = Decimal("0")
    currency: str = "EGP"
    quantity: int = 1

    @property
    def buy_total(self) -> Decimal:
        return (self.buy_price * self.quantity).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @property
    def sell_total(self) -> Decimal:
        return (self.sell_price * self.quantity).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @property
    def margin(self) -> Decimal:
        return (self.sell_total - self.buy_total).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @property
    def margin_pct(self) -> Decimal:
        if self.sell_total == 0:
            return Decimal("0")
        return ((self.margin / self.sell_total) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


class PassengerRecord(BaseModel):
    """A single validated passenger from the manifest."""

    full_name: str
    full_name_ar: str | None = None
    passport_number: str | None = None
    passport_expiry: str | None = None
    date_of_birth: str | None = None
    nationality: str | None = None
    gender: str | None = None
    passenger_type: str = "adult"


class CaseFinancials(BaseModel):
    """
    Typed summary of a travel booking's financial position.
    Produced by calculate_booking_financials() and consumed by the GL listener.

    Separation of concerns:
      total_buy_price   → DR Accounts Payable (supplier liability)
      total_sell_price  → CR Accounts Receivable (customer invoice)
      total_margin      → Net agency revenue (= sell - buy)
      commission_amount → Revenue line for agency's fee (if margin is split)
    """

    case_id: str
    currency: str = "EGP"

    # Aggregated financials
    total_buy_price: Decimal = Decimal("0")
    total_sell_price: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")
    margin_pct: Decimal = Decimal("0")

    # Commission separated from raw margin for transparent GL posting
    commission_amount: Decimal = Decimal("0")
    commission_pct: Decimal = Decimal("0")

    # Per-service breakdown
    service_lines: list[ServiceLine] = []

    # Passenger count
    passenger_count: int = 0
    passenger_manifest: list[PassengerRecord] = []

    @model_validator(mode="after")
    def _compute_derived(self) -> "CaseFinancials":
        if self.total_sell_price > 0:
            self.margin_pct = (
                (self.total_margin / self.total_sell_price) * 100
            ).quantize(Decimal("0.01"), ROUND_HALF_UP)
            self.commission_pct = (
                (self.commission_amount / self.total_sell_price) * 100
            ).quantize(Decimal("0.01"), ROUND_HALF_UP)
        return self


# ── Engine ─────────────────────────────────────────────────────────────────────


def calculate_booking_financials(
    case_id: str,
    case_data: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> CaseFinancials:
    """
    Pure function: extracts financial data from a travel Case's JSONB payload
    and returns a typed CaseFinancials summary.

    Resolution order for pricing:
      1. Per-service buy_price/sell_price from Case.data["services"]
      2. Top-level buy_price/sell_price from Case.data (set at quotation stage)
      3. Defaults to 0 if neither is present

    Commission calculation:
      - If explicit margin exists (sell > buy), commission = margin
      - If no service-level data, falls back to:
          commission = sell_price * default_commission_rate (from CaseType.meta)
    """
    meta = meta or {}
    currency = case_data.get("currency", "EGP")
    default_commission_rate = Decimal(str(meta.get("default_commission_rate", "0.10")))

    # ── Parse service lines ────────────────────────────────────────────────────
    raw_services: list[dict[str, Any]] = case_data.get("services") or []
    service_lines: list[ServiceLine] = []

    for svc in raw_services:
        if not isinstance(svc, dict):
            continue
        try:
            line = ServiceLine(
                service_type=svc.get("service_type", "other"),
                supplier_id=svc.get("supplier_id"),
                supplier_name=svc.get("supplier_name"),
                description=svc.get("description"),
                buy_price=Decimal(str(svc.get("buy_price", "0") or "0")),
                sell_price=Decimal(str(svc.get("sell_price", "0") or "0")),
                currency=svc.get("currency", currency),
                quantity=int(svc.get("quantity", 1) or 1),
            )
            service_lines.append(line)
        except Exception:
            # Skip malformed service entries; do not crash the financial engine
            continue

    # ── Aggregate totals ───────────────────────────────────────────────────────
    if service_lines:
        total_buy = sum(s.buy_total for s in service_lines)
        total_sell = sum(s.sell_total for s in service_lines)
    else:
        # Fall back to top-level quotation prices
        total_buy = Decimal(str(case_data.get("buy_price", "0") or "0"))
        total_sell = Decimal(str(case_data.get("sell_price", "0") or "0"))

    total_buy = total_buy.quantize(Decimal("0.01"), ROUND_HALF_UP)
    total_sell = total_sell.quantize(Decimal("0.01"), ROUND_HALF_UP)
    total_margin = (total_sell - total_buy).quantize(Decimal("0.01"), ROUND_HALF_UP)

    # Commission = explicit margin OR fallback rate on sell price
    if total_margin > 0:
        commission = total_margin
    elif total_sell > 0:
        commission = (total_sell * default_commission_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
    else:
        commission = Decimal("0")

    # ── Parse passenger manifest ───────────────────────────────────────────────
    raw_passengers: list[dict[str, Any]] = case_data.get("passenger_manifest") or []
    passengers: list[PassengerRecord] = []
    for p in raw_passengers:
        if not isinstance(p, dict):
            continue
        try:
            passengers.append(PassengerRecord(**{k: v for k, v in p.items() if v is not None}))
        except Exception:
            continue

    return CaseFinancials(
        case_id=case_id,
        currency=currency,
        total_buy_price=total_buy,
        total_sell_price=total_sell,
        total_margin=total_margin,
        commission_amount=commission,
        service_lines=service_lines,
        passenger_count=len(passengers) or case_data.get("group_size", 1),
        passenger_manifest=passengers,
    )
