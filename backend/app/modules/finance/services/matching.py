"""
app/modules/finance/services/matching.py — COD Settlement Matching Engine (FR-771, FR-772, FR-774, FR-775)

Implements:
  - parse_settlement_file: CSV / JSON parser for carrier settlement statements
  - match_settlement: Exact and fuzzy matching engine with exception categorization
  - generate_carrier_receivable_snapshot: Outstanding carrier receivable aging analysis
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.modules.contacts.models import Contact
from app.modules.finance.models.settlements import (
    CarrierReceivableSnapshot,
    CarrierSettlement,
    CarrierSettlementState,
    SettlementLine,
    SettlementLineExceptionType,
    SettlementLineMatchState,
)
from app.modules.logistics.models.carriers import Shipment
from app.modules.logistics.services.shipments import ShipmentState
from app.modules.sales.models.invoice import SalesInvoice as Invoice

logger = logging.getLogger(__name__)

FOUR_DECIMALS = Decimal("0.0001")


class SettlementFileParseError(ValueError):
    """Raised when a carrier settlement statement cannot be parsed correctly."""


def parse_settlement_file(content: bytes, filename: str) -> list[dict[str, Any]]:
    """
    Parse a carrier settlement file (CSV or JSON format) into standardized line dictionaries.
    Supports Arabic/English header variations automatically.
    """
    filename_lower = filename.lower()
    if filename_lower.endswith(".json"):
        try:
            data = json.loads(content.decode("utf-8"))
            if not isinstance(data, list):
                raise SettlementFileParseError("JSON settlement file must contain an array of objects.")
            return [_normalize_row(row) for row in data]
        except Exception as exc:
            raise SettlementFileParseError(f"Failed to parse JSON settlement file: {exc}") from exc
    elif filename_lower.endswith(".csv") or filename_lower.endswith(".txt"):
        try:
            text_content = content.decode("utf-8-sig")  # strip BOM if present
            reader = csv.DictReader(io.StringIO(text_content))
            return [_normalize_row(dict(row)) for row in reader]
        except Exception as exc:
            raise SettlementFileParseError(f"Failed to parse CSV settlement file: {exc}") from exc
    else:
        raise SettlementFileParseError("Unsupported file format. Please upload CSV or JSON.")


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map Arabic and English header names to canonical fields."""
    normalized: dict[str, Any] = {}
    key_map = {
        "awb_number": ["awb_number", "awb", "tracking_number", "tracking", "رقم_بوليصة", "بوليصة"],
        "cod_collected": ["cod_collected", "cod_amount", "amount", "cod", "المبلغ_المحصل", "تحصيل"],
        "shipping_fee": ["shipping_fee", "delivery_fee", "shipping", "رسوم_الشحن", "شحن"],
        "cod_fee": ["cod_fee", "collection_fee", "cash_fee", "رسوم_التحصيل"],
        "return_fee": ["return_fee", "return_cost", "رسوم_المرتجع"],
        "phone_tail": ["phone_tail", "phone_last4", "phone", "هاتف", "رقم_الهاتف"],
        "notes": ["notes", "remarks", "description", "ملاحظات"],
    }

    for can_key, aliases in key_map.items():
        val = None
        for alias in aliases:
            for row_key, row_val in row.items():
                if row_key and row_key.strip().lower() == alias:
                    val = row_val
                    break
            if val is not None:
                break
        normalized[can_key] = val

    return {
        "awb_number": str(normalized.get("awb_number") or "").strip(),
        "cod_collected": _to_decimal(normalized.get("cod_collected"), "0.0000"),
        "shipping_fee": _to_decimal(normalized.get("shipping_fee"), "0.0000"),
        "cod_fee": _to_decimal(normalized.get("cod_fee"), "0.0000"),
        "return_fee": _to_decimal(normalized.get("return_fee"), "0.0000"),
        "phone_tail": str(normalized.get("phone_tail") or "").strip()[-4:]
        if normalized.get("phone_tail")
        else "",
        "notes": str(normalized.get("notes") or "").strip(),
    }


def _to_decimal(val: Any, default: str = "0.0000") -> Decimal:
    if val is None or val == "":
        return Decimal(default)
    try:
        return Decimal(str(val).replace(",", "").strip()).quantize(FOUR_DECIMALS)
    except Exception:
        return Decimal(default)


async def match_settlement(
    session: AsyncSession,
    carrier_code: str,
    settlement_ref: str,
    lines: list[dict[str, Any]],
    tolerance: Decimal = Decimal("5.0000"),
    date_window_days: int = 7,
) -> CarrierSettlement:
    """
    Reconcile carrier settlement statement lines against shipments (FR-771, FR-772, FR-774).
    Applies Exact Matching first, then Fuzzy Matching for unmatched AWBs, and categorizes exceptions.
    """
    carrier_code_norm = carrier_code.strip().lower()

    # Step 1: Create header
    settlement = CarrierSettlement(
        carrier_code=carrier_code_norm,
        settlement_ref=settlement_ref,
        state=CarrierSettlementState.IMPORTED,
    )
    session.add(settlement)
    await session.flush()

    total_gross = Decimal("0.0000")
    total_fees = Decimal("0.0000")

    matched_count = 0
    unmatched_count = 0
    disputed_count = 0

    for raw_line in lines:
        awb = raw_line["awb_number"]
        cod_collected = raw_line["cod_collected"]
        shipping_fee = raw_line["shipping_fee"]
        cod_fee = raw_line["cod_fee"]
        return_fee = raw_line["return_fee"]
        phone_tail = raw_line.get("phone_tail", "")
        notes = raw_line.get("notes", "")

        net_remitted = cod_collected - (shipping_fee + cod_fee + return_fee)

        total_gross += cod_collected
        total_fees += shipping_fee + cod_fee + return_fee

        s_line = SettlementLine(
            settlement_id=settlement.id,
            awb_number=awb,
            cod_collected=cod_collected,
            shipping_fee=shipping_fee,
            cod_fee=cod_fee,
            return_fee=return_fee,
            net_remitted=net_remitted,
            notes=notes,
        )

        # ── Exact Match Lookup (FR-771) ───────────────────────────────────────
        stmt_exact = select(Shipment).where(
            Shipment.carrier_code == carrier_code_norm,
            Shipment.awb_number == awb,
        )
        res_exact = await session.execute(stmt_exact)
        shipment = res_exact.scalars().first()

        if shipment is not None:
            # Check state
            if shipment.state != ShipmentState.DELIVERED:
                s_line.match_state = SettlementLineMatchState.UNMATCHED
                s_line.exception_type = SettlementLineExceptionType.REMITTED_BUT_NOT_DELIVERED
                s_line.notes = f"Shipment state is {shipment.state.value}, not DELIVERED. {notes}".strip()
                unmatched_count += 1
            # Check amount mismatch
            elif abs(shipment.cod_amount - cod_collected) > tolerance:
                s_line.match_state = SettlementLineMatchState.DISPUTED
                s_line.exception_type = SettlementLineExceptionType.AMOUNT_MISMATCH
                s_line.shipment_id = shipment.id
                s_line.notes = (
                    f"COD amount mismatch (expected {shipment.cod_amount}, got {cod_collected}). {notes}".strip()
                )
                disputed_count += 1
            else:
                s_line.match_state = SettlementLineMatchState.MATCHED
                s_line.exception_type = SettlementLineExceptionType.NONE
                s_line.shipment_id = shipment.id
                matched_count += 1
        else:
            # ── Fuzzy Match Lookup (FR-772) ───────────────────────────────────
            # Try matching on amount within tolerance + date window + phone-tail
            fuzzy_candidate = await _attempt_fuzzy_match(
                session=session,
                carrier_code=carrier_code_norm,
                cod_collected=cod_collected,
                phone_tail=phone_tail,
                tolerance=tolerance,
                date_window_days=date_window_days,
            )

            if fuzzy_candidate is not None:
                s_line.match_state = SettlementLineMatchState.FUZZY_MATCHED
                s_line.exception_type = SettlementLineExceptionType.NONE
                s_line.shipment_id = fuzzy_candidate.id
                s_line.notes = f"Fuzzy matched to shipment AWB {fuzzy_candidate.awb_number}. {notes}".strip()
                matched_count += 1
            else:
                # Exception Queue (FR-774)
                s_line.match_state = SettlementLineMatchState.UNMATCHED
                s_line.exception_type = SettlementLineExceptionType.UNKNOWN_AWB
                s_line.notes = f"No shipment matched exact AWB or fuzzy criteria. {notes}".strip()
                unmatched_count += 1

        session.add(s_line)

    settlement.gross_amount = total_gross
    settlement.total_fees = total_fees
    settlement.net_amount = total_gross - total_fees

    # Determine overall settlement state
    total_lines = len(lines)
    if total_lines == 0 or (unmatched_count == 0 and disputed_count == 0):
        settlement.state = CarrierSettlementState.MATCHED
    elif matched_count > 0:
        settlement.state = CarrierSettlementState.PARTIALLY_MATCHED
    else:
        settlement.state = CarrierSettlementState.DISPUTED

    await session.flush()
    return settlement


async def _attempt_fuzzy_match(
    session: AsyncSession,
    carrier_code: str,
    cod_collected: Decimal,
    phone_tail: str,
    tolerance: Decimal,
    date_window_days: int,
) -> Shipment | None:
    """
    Attempt fuzzy matching on (amount + tolerance) AND (date window) AND (phone-tail).
    Returns the candidate Shipment if exactly one unambiguous candidate is found.
    """
    min_amount = cod_collected - tolerance
    max_amount = cod_collected + tolerance
    min_date = datetime.now(UTC) - timedelta(days=date_window_days)

    stmt = select(Shipment).where(
        Shipment.carrier_code == carrier_code,
        Shipment.state == ShipmentState.DELIVERED,
        Shipment.cod_amount >= min_amount,
        Shipment.cod_amount <= max_amount,
        Shipment.created_at >= min_date,
    )
    res = await session.execute(stmt)
    candidates = list(res.scalars().all())

    if not candidates:
        return None

    if not phone_tail or len(phone_tail) < 4:
        # If no phone tail is provided, only return candidate if there is exactly one amount match
        if len(candidates) == 1:
            return candidates[0]
        return None

    # Filter candidates by customer phone tail
    matched_candidates: list[Shipment] = []
    for cand in candidates:
        inv_stmt = select(Invoice).where(Invoice.id == cand.invoice_id)
        inv_res = await session.execute(inv_stmt)
        invoice = inv_res.scalars().first()
        if invoice and invoice.contact_id:
            cont_stmt = select(Contact).where(Contact.id == invoice.contact_id)
            cont_res = await session.execute(cont_stmt)
            contact = cont_res.scalars().first()
            if contact and (
                (contact.phone and contact.phone.endswith(phone_tail))
                or (contact.phone_e164 and contact.phone_e164.endswith(phone_tail))
            ):
                matched_candidates.append(cand)

    if len(matched_candidates) == 1:
        return matched_candidates[0]

    return None


async def generate_carrier_receivable_snapshot(
    session: AsyncSession,
    carrier_code: str,
) -> CarrierReceivableSnapshot:
    """
    Generate an aging snapshot for all DELIVERED COD shipments that remain unsettled (FR-775).
    Aging brackets: 0-7 days, 8-14 days, 15-30 days, 30+ days.
    """
    carrier_code_norm = carrier_code.strip().lower()

    # Find all shipments for this carrier in DELIVERED state
    stmt = select(Shipment).where(
        Shipment.carrier_code == carrier_code_norm,
        Shipment.state == ShipmentState.DELIVERED,
        Shipment.cod_amount > 0,
    )
    res = await session.execute(stmt)
    delivered_shipments = list(res.scalars().all())

    # Find which shipment IDs are already reconciled/posted
    settled_stmt = (
        select(SettlementLine.shipment_id)
        .join(
            CarrierSettlement,
            SettlementLine.settlement_id == CarrierSettlement.id,
        )
        .where(
            CarrierSettlement.carrier_code == carrier_code_norm,
            CarrierSettlement.state.in_(
                [CarrierSettlementState.MATCHED, CarrierSettlementState.POSTED],
            ),
            col(SettlementLine.shipment_id).is_not(None),
        )
    )
    settled_res = await session.execute(settled_stmt)
    settled_ids = set(settled_res.scalars().all())

    today = date.today()
    snapshot = CarrierReceivableSnapshot(
        carrier_code=carrier_code_norm,
        snapshot_date=today,
    )

    for ship in delivered_shipments:
        if ship.id in settled_ids:
            continue
        snapshot.unsettled_shipments_count += 1
        snapshot.total_outstanding_cod += ship.cod_amount

        age_days = (today - ship.created_at.date()).days
        if age_days <= 7:
            snapshot.aging_0_7_days += ship.cod_amount
        elif age_days <= 14:
            snapshot.aging_8_14_days += ship.cod_amount
        elif age_days <= 30:
            snapshot.aging_15_30_days += ship.cod_amount
        else:
            snapshot.aging_30_plus_days += ship.cod_amount

    session.add(snapshot)
    await session.flush()
    return snapshot
