"""
app/plugins/hospitality/services/folio.py — Folio & Extras Engine

Calculates the consolidated hotel bill for a room reservation.
Produces a typed FolioSummary that the GL listener consumes at checkout.

Charge composition:
  1. Room charge   = daily_rate × nights_stayed × (1 + service_charge_rate)
  2. Board charges = if board_type includes meals, adds per-person per-night rate
  3. Extras        = sum of all FolioItem rows (restaurant, laundry, minibar, etc.)
  4. Tax           = (room + extras) × tax_rate

DECOUPLING CONTRACT:
  ✅ Reads Case.data and FolioItem rows — no accounting imports
  ✅ Returns typed Pydantic model; GL listener handles journal entries
  ❌ Never writes JournalEntry rows directly
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.plugins.hospitality.models.folio import FolioItem, FolioItemCategory

# ── Board supplement rates (EGP per person per night) — overridden by tenant config ──

_DEFAULT_BOARD_SUPPLEMENTS: dict[str, Decimal] = {
    "room_only": Decimal("0"),
    "bed_breakfast": Decimal("150"),
    "half_board": Decimal("350"),
    "full_board": Decimal("600"),
    "all_inclusive": Decimal("900"),
}


# ── Typed output models ────────────────────────────────────────────────────────


class FolioLineOut(BaseModel):
    """A single summarised charge line for display / GL posting."""
    category: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    currency: str
    charge_date: str | None = None


class FolioSummary(BaseModel):
    """
    Complete financial summary for one room reservation.
    Consumed by the checkout listener to post GL entries.
    """
    case_id: str
    currency: str = "EGP"

    # Nights
    nights: int
    check_in: str
    check_out: str

    # Component subtotals
    room_charge: Decimal       # daily_rate × nights × (1 + service_charge_rate)
    board_charge: Decimal      # meal supplement × guests × nights
    extras_total: Decimal      # all FolioItem extras
    discount_total: Decimal    # sum of DISCOUNT lines (negative)
    deposit_total: Decimal     # sum of DEPOSIT lines (treated as offsets)

    # Tax & charges
    service_charge: Decimal
    tax_amount: Decimal
    tax_rate: Decimal
    service_charge_rate: Decimal

    # Grand total
    subtotal: Decimal          # room + board + extras + discount
    total: Decimal             # subtotal + service_charge + tax
    balance_due: Decimal       # total − deposits received

    # Per-line breakdown for the receipt printout
    lines: list[FolioLineOut] = []


# ── Engine ─────────────────────────────────────────────────────────────────────


def _nights_between(start: date, end: date) -> int:
    """Number of nights between check-in and check-out. Minimum 1."""
    delta = (end - start).days
    return max(delta, 1)


def _to_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            # Accept both "YYYY-MM-DD" and ISO datetime strings
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


async def calculate_folio_total(
    session: AsyncSession,
    case_id: uuid.UUID,
    case_data: dict[str, Any],
    case_start: Any,   # Case.start_date (check-in)
    case_end: Any,     # Case.end_date   (check-out)
    meta: dict[str, Any] | None = None,
) -> FolioSummary:
    """
    Builds a complete FolioSummary by:
      1. Computing the room charge from case data (daily_rate × nights)
      2. Adding board supplement (board_type × guest_count × nights)
      3. Fetching and summing all FolioItem rows
      4. Applying tax and service charge

    This function is async because it queries FolioItem rows from the DB.
    The result is pure data — no writes, no GL operations.
    """
    meta = meta or {}
    currency = case_data.get("currency", "EGP")

    # ── Date computation ───────────────────────────────────────────────────────
    ci = _to_date(case_start)
    co = _to_date(case_end) or date.today()
    if not ci:
        ci = date.today()
    nights = _nights_between(ci, co)

    # ── Rates ──────────────────────────────────────────────────────────────────
    daily_rate = Decimal(str(case_data.get("daily_rate", "0") or "0"))
    guest_count = int(case_data.get("guest_count", 1) or 1)
    board_type = case_data.get("board_type", "room_only")
    breakfast_rate = Decimal(str(case_data.get("breakfast_rate_per_person", "0") or "0"))

    tax_rate = Decimal(str(meta.get("tax_rate", "0.14")))
    svc_rate = Decimal(str(meta.get("service_charge_rate", "0.12")))

    # ── 1. Room Charge ─────────────────────────────────────────────────────────
    room_subtotal = (daily_rate * Decimal(nights)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    service_charge_on_room = (room_subtotal * svc_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

    lines: list[FolioLineOut] = [
        FolioLineOut(
            category=FolioItemCategory.ROOM_CHARGE,
            description=f"إيجار الغرفة ({nights} ليلة × {daily_rate} {currency})",
            quantity=Decimal(nights),
            unit_price=daily_rate,
            amount=room_subtotal,
            currency=currency,
        )
    ]

    # ── 2. Board Supplement ────────────────────────────────────────────────────
    board_supplement: Decimal
    if breakfast_rate > 0:
        board_supplement = (breakfast_rate * Decimal(guest_count) * Decimal(nights)).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )
    else:
        default_rate = _DEFAULT_BOARD_SUPPLEMENTS.get(board_type, Decimal("0"))
        board_supplement = (default_rate * Decimal(guest_count) * Decimal(nights)).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )

    if board_supplement > 0:
        board_label = {
            "bed_breakfast": "إفطار",
            "half_board": "نصف إقامة",
            "full_board": "إقامة كاملة",
            "all_inclusive": "شامل كل شيء",
        }.get(board_type, board_type)
        lines.append(
            FolioLineOut(
                category="restaurant",
                description=f"{board_label} ({guest_count} ضيف × {nights} ليالي)",
                quantity=Decimal(guest_count * nights),
                unit_price=breakfast_rate or _DEFAULT_BOARD_SUPPLEMENTS.get(board_type, Decimal("0")),
                amount=board_supplement,
                currency=currency,
            )
        )

    # ── 3. FolioItem extras from DB ────────────────────────────────────────────
    items_stmt = select(FolioItem).where(FolioItem.case_id == case_id)
    folio_items = (await session.scalars(items_stmt)).all()

    extras_total = Decimal("0")
    discount_total = Decimal("0")
    deposit_total = Decimal("0")

    for item in folio_items:
        amount = item.amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
        lines.append(
            FolioLineOut(
                category=item.category.value,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=amount,
                currency=item.currency,
                charge_date=item.charge_date.date().isoformat() if item.charge_date else None,
            )
        )
        if item.category == FolioItemCategory.DISCOUNT:
            discount_total += amount   # Expected to be negative
        elif item.category == FolioItemCategory.DEPOSIT:
            deposit_total += abs(amount)
        else:
            extras_total += amount

    # ── 4. Tax & Service Charge ────────────────────────────────────────────────
    subtotal = (room_subtotal + board_supplement + extras_total + discount_total).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )
    service_charge = (subtotal * svc_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
    tax_amount = ((subtotal + service_charge) * tax_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
    total = (subtotal + service_charge + tax_amount).quantize(Decimal("0.01"), ROUND_HALF_UP)
    balance_due = (total - deposit_total).quantize(Decimal("0.01"), ROUND_HALF_UP)

    # Append tax and service charge lines
    lines.extend([
        FolioLineOut(
            category=FolioItemCategory.SERVICE_CHARGE,
            description=f"رسوم الخدمة ({int(svc_rate * 100)}٪)",
            quantity=Decimal("1"),
            unit_price=service_charge,
            amount=service_charge,
            currency=currency,
        ),
        FolioLineOut(
            category=FolioItemCategory.TAX,
            description=f"ضريبة القيمة المضافة ({int(tax_rate * 100)}٪)",
            quantity=Decimal("1"),
            unit_price=tax_amount,
            amount=tax_amount,
            currency=currency,
        ),
    ])

    return FolioSummary(
        case_id=str(case_id),
        currency=currency,
        nights=nights,
        check_in=ci.isoformat(),
        check_out=co.isoformat(),
        room_charge=room_subtotal,
        board_charge=board_supplement,
        extras_total=extras_total,
        discount_total=discount_total,
        deposit_total=deposit_total,
        service_charge=service_charge,
        tax_amount=tax_amount,
        tax_rate=tax_rate,
        service_charge_rate=svc_rate,
        subtotal=subtotal,
        total=total,
        balance_due=balance_due,
        lines=lines,
    )


async def post_extra_charge(
    session: AsyncSession,
    case_id: uuid.UUID,
    category: FolioItemCategory,
    description: str,
    amount: Decimal,
    currency: str = "EGP",
    quantity: Decimal = Decimal("1"),
    posted_by: str | None = None,
    notes: str | None = None,
) -> FolioItem:
    """
    Convenience function to add a single extra charge to the folio.
    Returns the persisted FolioItem (caller is responsible for commit).
    """
    item = FolioItem(
        case_id=case_id,
        category=category,
        description=description,
        quantity=quantity,
        unit_price=(amount / quantity).quantize(Decimal("0.0001"), ROUND_HALF_UP) if quantity else amount,
        amount=(amount * quantity).quantize(Decimal("0.01"), ROUND_HALF_UP),
        currency=currency,
        posted_by=posted_by,
        notes=notes,
    )
    session.add(item)
    await session.flush()
    return item
