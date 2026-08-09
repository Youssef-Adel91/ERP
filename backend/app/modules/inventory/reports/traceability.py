from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc
from app.core.reports.decorators import reporting_tool

from app.modules.inventory.models.core import (
    Batch,
    CostLayer,
    Item,
    SerialNumber,
    StockMovement,
    Warehouse,
)


@reporting_tool(
    name="Serial Genealogy Report",
    description_ar="تقرير تتبع الرقم التسلسلي",
    required_permission="inventory.reports.traceability"
)
async def get_serial_genealogy(session: AsyncSession, serial_id: UUID) -> dict:
    """
    Returns the complete chronological history of a serial number (FR-344).
    Includes inbounds, outbounds, and transfers.
    """
    serial = await session.get(SerialNumber, serial_id)
    if not serial:
        raise ValueError(f"Serial number {serial_id} not found")

    item = await session.get(Item, serial.item_id)

    stmt = (
        select(StockMovement, Warehouse)
        .join(Warehouse, StockMovement.warehouse_id == Warehouse.id)
        .where(StockMovement.serial_id == serial_id)
        .order_by(StockMovement.occurred_at.asc())
    )
    result = await session.execute(stmt)
    movements_data = result.all()

    history = []
    for mov, wh in movements_data:
        history.append({
            "movement_id": mov.id,
            "occurred_at": mov.occurred_at,
            "movement_type": mov.movement_type,
            "quantity": mov.qty,
            "warehouse_name": wh.name,
            "warehouse_type": wh.type,
            "reference_id": mov.reference_id,
            "contact_id": mov.contact_id,
        })

    return {
        "serial_no": serial.serial_no,
        "item_sku": item.sku if item else None,
        "current_state": serial.state,
        "current_owner_contact_id": serial.current_owner_contact_id,
        "history": history
    }


@reporting_tool(
    name="Batch Traceability Report",
    description_ar="تقرير تتبع رقم التشغيلة",
    required_permission="inventory.reports.traceability"
)
async def get_batch_traceability(session: AsyncSession, batch_id: UUID) -> dict:
    """
    Bidirectional trace for a batch (FR-355).
    Separates inbound (receipts from suppliers) and outbound (sales to customers).
    """
    batch = await session.get(Batch, batch_id)
    if not batch:
        raise ValueError(f"Batch {batch_id} not found")

    item = await session.get(Item, batch.item_id)

    stmt = (
        select(StockMovement, Warehouse)
        .join(Warehouse, StockMovement.warehouse_id == Warehouse.id)
        .where(StockMovement.batch_id == batch_id)
        .order_by(StockMovement.occurred_at.asc())
    )
    result = await session.execute(stmt)
    movements_data = result.all()

    inbounds = []
    outbounds = []
    adjustments = []

    for mov, wh in movements_data:
        record = {
            "movement_id": mov.id,
            "occurred_at": mov.occurred_at,
            "quantity": mov.qty,
            "warehouse_name": wh.name,
            "reference_id": mov.reference_id,
            "contact_id": mov.contact_id,
        }
        
        if mov.movement_type == "IN":
            inbounds.append(record)
        elif mov.movement_type == "OUT":
            outbounds.append(record)
        else:
            adjustments.append(record)

    return {
        "batch_no": batch.batch_no,
        "item_sku": item.sku if item else None,
        "status": batch.status,
        "manufacture_date": batch.manufacture_date,
        "expiry_date": batch.expiry_date,
        "inbounds": inbounds,
        "outbounds": outbounds,
        "adjustments": adjustments
    }
