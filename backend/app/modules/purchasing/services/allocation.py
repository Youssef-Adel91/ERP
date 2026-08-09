"""
app/modules/purchasing/services/allocation.py — Landed Cost Allocation Engine

Implements:
  1. calculate_exact_allocations:
     - Computes pro-rata allocation across GoodsReceiptLine items based on AllocationBasis
     - Uses the Largest Remainder Method to allocate indivisible fractional piastres without rounding drift
     - Enforces strict `assert SUM(allocations) == cost_line_amount`
  2. create_import_shipment:
     - Creates ImportShipment and LandedCostLine items, computes SHA-256 approvable hash (FR-1212)
  3. allocate_shipment_costs:
     - Generates LandedCostAllocation DB records and updates GoodsReceiptLine.expected_landed_unit_cost
  4. post_landed_costs:
     - Posts shipment and emits purchase.landed_cost_allocated outbox event for GL bridge consumption
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_DOWN
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.events.event_bus import DomainEvent, get_event_bus
from app.core.models.mixins import DocumentState
from app.modules.purchasing.exceptions import (
    ImportShipmentNotFoundError,
    LandedCostAllocationError,
)
from app.modules.purchasing.models.core import GoodsReceipt, GoodsReceiptLine, GoodsReceiptStatus
from app.modules.purchasing.models.landed_cost import (
    AllocationBasis,
    ImportShipment,
    ImportShipmentStage,
    ImportShipmentStatus,
    LandedCostAllocation,
    LandedCostLine,
    LandedCostType,
)

event_bus = get_event_bus()


def calculate_exact_allocations(
    cost_line_amount: Decimal,
    grn_lines: list[GoodsReceiptLine],
    allocation_basis: AllocationBasis,
) -> list[dict[str, Any]]:
    """
    Allocate a LandedCostLine amount across target GoodsReceiptLines using the
    Largest Remainder Method (Hamilton method) to ensure piastre-exact allocation.

    Step 1: Calculate pro-rata share based on allocation_basis weight.
    Step 2: Quantize/Round each allocation DOWN to 4 decimal places.
    Step 3: Calculate the exact residue (cost_line_amount - SUM(rounded_allocations)).
    Step 4: Add the exact residue to the GRN line that had the largest original basis weight.
    Step 5: Strictly assert SUM(allocations) == cost_line_amount before returning.
    """
    if not grn_lines:
        raise LandedCostAllocationError("No target GRN lines provided for landed cost allocation.")

    cost_line_amount = Decimal(str(cost_line_amount)).quantize(Decimal("0.0001"))
    if cost_line_amount < 0:
        raise LandedCostAllocationError("Cost line amount cannot be negative.")

    # 1. Determine basis weight for each line
    weights: list[Decimal] = []
    for line in grn_lines:
        qty = Decimal(str(line.qty_received))
        if allocation_basis == AllocationBasis.VALUE:
            cost = Decimal(str(line.unit_cost_estimated or Decimal("0.0000")))
            w = (qty * cost).quantize(Decimal("0.0001"))
        elif allocation_basis == AllocationBasis.QTY:
            w = qty.quantize(Decimal("0.0001"))
        elif allocation_basis == AllocationBasis.WEIGHT:
            val = getattr(line, "weight", None)
            w = Decimal(str(val if val is not None else qty)).quantize(Decimal("0.0001"))
        elif allocation_basis == AllocationBasis.VOLUME:
            val = getattr(line, "volume", None)
            w = Decimal(str(val if val is not None else qty)).quantize(Decimal("0.0001"))
        else:
            w = qty.quantize(Decimal("0.0001"))
        weights.append(w)

    total_weight = sum(weights)
    if total_weight <= 0:
        # Fallback to equal weights if all items have 0 basis weight
        weights = [Decimal("1.0000") for _ in grn_lines]
        total_weight = Decimal(str(len(grn_lines)))

    # 2. Pro-rata exact & quantize DOWN to 4 decimals
    allocations: list[dict[str, Any]] = []
    for line, w in zip(grn_lines, weights):
        pro_rata = cost_line_amount * (w / total_weight)
        rounded = pro_rata.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
        allocations.append({
            "target_grn_line_id": line.id,
            "basis_weight": w,
            "pro_rata_exact": pro_rata,
            "allocated_amount": rounded,
        })

    # 3. Calculate residue
    sum_rounded = sum(a["allocated_amount"] for a in allocations)
    residue = cost_line_amount - sum_rounded

    # 4. Add residue to line with the largest original basis weight
    if residue != Decimal("0.0000"):
        largest_idx = max(range(len(grn_lines)), key=lambda i: weights[i])
        allocations[largest_idx]["allocated_amount"] += residue

    # 5. Strict invariant assertion
    total_allocated = sum(a["allocated_amount"] for a in allocations)
    assert total_allocated == cost_line_amount, (
        f"Landed cost allocation drift detected: SUM(allocations)={total_allocated} != cost_amount={cost_line_amount}"
    )

    return allocations


async def create_import_shipment(
    session: AsyncSession,
    shipment_ref: str,
    supplier_ids: list[UUID | str],
    po_ids: list[UUID | str],
    currency: str = "EGP",
    fx_rate: Decimal = Decimal("1.0000"),
    lines_data: list[dict[str, Any]] | None = None,
) -> ImportShipment:
    """Create a new ImportShipment document in DRAFT status with SHA-256 approvable hash."""
    lines_data = lines_data or []
    norm_suppliers = [str(sid) for sid in supplier_ids]
    norm_pos = [str(pid) for pid in po_ids]

    total_cost = Decimal("0.0000")
    for l_data in lines_data:
        total_cost += Decimal(str(l_data["amount"]))
    total_cost = total_cost.quantize(Decimal("0.0001"))

    # FR-1212 SHA-256 deterministic content hashing
    hash_payload = {
        "shipment_ref": shipment_ref,
        "supplier_ids": sorted(norm_suppliers),
        "po_ids": sorted(norm_pos),
        "total_landed_cost": str(total_cost),
        "lines": [
            {
                "cost_type": str(l["cost_type"]),
                "amount": str(l["amount"]),
                "allocation_basis": str(l.get("allocation_basis", "VALUE")),
            }
            for l in lines_data
        ],
    }
    content_hash = hashlib.sha256(
        json.dumps(hash_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

    shipment = ImportShipment(
        shipment_ref=shipment_ref,
        supplier_ids=norm_suppliers,
        po_ids=norm_pos,
        stage=ImportShipmentStage.DRAFT,
        status=ImportShipmentStatus.DRAFT,
        state=DocumentState.DRAFT,
        currency=currency,
        fx_rate=fx_rate,
        total_landed_cost=total_cost,
        content_hash=content_hash,
    )
    session.add(shipment)
    await session.flush()

    for l_data in lines_data:
        line = LandedCostLine(
            shipment_id=shipment.id,
            cost_type=l_data["cost_type"],
            amount=Decimal(str(l_data["amount"])).quantize(Decimal("0.0001")),
            currency=l_data.get("currency", currency),
            fx_rate=Decimal(str(l_data.get("fx_rate", fx_rate))),
            allocation_basis=l_data.get("allocation_basis", AllocationBasis.VALUE),
        )
        session.add(line)

    await session.flush()

    stmt = (
        select(ImportShipment)
        .where(ImportShipment.id == shipment.id)
        .options(selectinload(ImportShipment.lines))
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def allocate_shipment_costs(
    session: AsyncSession,
    shipment_id: UUID | str,
    grn_lines: list[GoodsReceiptLine] | None = None,
) -> list[LandedCostAllocation]:
    """
    Allocate all LandedCostLines in an ImportShipment across target GoodsReceiptLine items
    and persist LandedCostAllocation records to the DB.
    """
    if isinstance(shipment_id, str):
        shipment_id = UUID(shipment_id)

    stmt = (
        select(ImportShipment)
        .where(ImportShipment.id == shipment_id)
        .options(selectinload(ImportShipment.lines))
    )
    res = await session.execute(stmt)
    shipment = res.scalar_one_or_none()
    if not shipment:
        raise ImportShipmentNotFoundError(shipment_id)

    if grn_lines is None:
        po_uuids = [UUID(str(pid)) for pid in shipment.po_ids]
        stmt_grn = (
            select(GoodsReceiptLine)
            .join(GoodsReceipt, GoodsReceiptLine.grn_id == GoodsReceipt.id)
            .where(GoodsReceipt.po_id.in_(po_uuids))
        )
        res_grn = await session.execute(stmt_grn)
        grn_lines = list(res_grn.scalars().all())

    if not grn_lines:
        raise LandedCostAllocationError(
            f"No target GoodsReceiptLine records found for ImportShipment '{shipment.shipment_ref}'."
        )

    all_allocations: list[LandedCostAllocation] = []
    line_total_allocations: dict[UUID, Decimal] = {line.id: Decimal("0.0000") for line in grn_lines}

    for cost_line in shipment.lines:
        line_allocs = calculate_exact_allocations(
            cost_line_amount=cost_line.amount,
            grn_lines=grn_lines,
            allocation_basis=cost_line.allocation_basis,
        )
        for alloc_dict in line_allocs:
            alloc_obj = LandedCostAllocation(
                landed_cost_line_id=cost_line.id,
                target_grn_line_id=alloc_dict["target_grn_line_id"],
                allocated_amount=alloc_dict["allocated_amount"],
            )
            session.add(alloc_obj)
            all_allocations.append(alloc_obj)
            line_total_allocations[alloc_dict["target_grn_line_id"]] += alloc_dict["allocated_amount"]

    # Update expected_landed_unit_cost on target GRN lines
    for line in grn_lines:
        if line.qty_received > Decimal("0.0000"):
            base_cost = line.unit_cost_estimated or Decimal("0.0000")
            add_on = (line_total_allocations[line.id] / line.qty_received).quantize(Decimal("0.0001"))
            line.expected_landed_unit_cost = base_cost + add_on
        session.add(line)

    await session.flush()
    return all_allocations


async def post_landed_costs(
    session: AsyncSession,
    shipment_id: UUID | str,
    grn_lines: list[GoodsReceiptLine] | None = None,
) -> ImportShipment:
    """
    Post an ImportShipment:
      1. Performs exact landed cost allocations across target GRN items.
      2. Transitions shipment status to POSTED / CLEARED.
      3. Emits 'purchase.landed_cost_allocated' domain event via the Outbox.
    """
    if isinstance(shipment_id, str):
        shipment_id = UUID(shipment_id)

    stmt = (
        select(ImportShipment)
        .where(ImportShipment.id == shipment_id)
        .options(selectinload(ImportShipment.lines))
    )
    res = await session.execute(stmt)
    shipment = res.scalar_one_or_none()
    if not shipment:
        raise ImportShipmentNotFoundError(shipment_id)

    allocations = await allocate_shipment_costs(session, shipment.id, grn_lines=grn_lines)

    shipment.status = ImportShipmentStatus.POSTED
    shipment.state = DocumentState.POSTED
    shipment.stage = ImportShipmentStage.CLEARED
    session.add(shipment)
    await session.flush()

    # Emit domain event for GL bridge consumption
    payload = {
        "shipment_id": str(shipment.id),
        "shipment_ref": shipment.shipment_ref,
        "total_landed_cost": str(shipment.total_landed_cost),
        "currency": shipment.currency,
        "fx_rate": str(shipment.fx_rate),
        "allocations": [
            {
                "landed_cost_line_id": str(alloc.landed_cost_line_id),
                "target_grn_line_id": str(alloc.target_grn_line_id),
                "allocated_amount": str(alloc.allocated_amount),
            }
            for alloc in allocations
        ],
    }

    event = DomainEvent(
        event_type="purchase.landed_cost_allocated",
        tenant_id=str(getattr(shipment, "tenant_id", "system")),
        payload=payload,
    )
    await event_bus.publish(event, session=session)

    return shipment
