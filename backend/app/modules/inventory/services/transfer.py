import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.inventory.models import (
    CostLayer,
    StockLevel,
    StockMovement,
    StockTransfer,
    StockTransferLine,
    TransferStatus,
    Warehouse,
    WarehouseType,
)
from app.modules.inventory.services.costing import CostingRequest, consume_stock

logger = logging.getLogger(__name__)


@dataclass
class ReceiptLine:
    line_id: UUID
    qty_received: Decimal


async def dispatch_transfer(session: AsyncSession, transfer_id: UUID) -> StockTransfer:
    """
    Dispatches a stock transfer from the source warehouse to the transit warehouse.
    Uses Phase 1a costing logic to consume stock and exactly carry over the cost to transit.
    """
    transfer = (await session.execute(
        select(StockTransfer).where(StockTransfer.id == transfer_id).with_for_update()
    )).scalar_one_or_none()

    if not transfer:
        raise ValueError(f"Transfer {transfer_id} not found")

    if transfer.status != TransferStatus.DRAFT:
        raise ValueError(f"Cannot dispatch transfer in status {transfer.status}")

    transit_warehouse = (await session.execute(
        select(Warehouse).where(Warehouse.id == transfer.transit_warehouse_id)
    )).scalar_one()

    if transit_warehouse.type != WarehouseType.TRANSIT:
        raise ValueError("Transit warehouse must be of type TRANSIT")

    lines = (await session.execute(
        select(StockTransferLine).where(StockTransferLine.transfer_id == transfer_id)
    )).scalars().all()

    if not lines:
        raise ValueError("Transfer has no lines")

    costing_requests = []
    for line in lines:
        if line.qty_dispatched <= 0:
            raise ValueError(f"Line {line.id} has invalid dispatch quantity")

        costing_requests.append(
            CostingRequest(
                item_id=line.item_id,
                variant_id=line.variant_id,
                warehouse_id=transfer.source_warehouse_id,
                quantity=line.qty_dispatched,
                movement_type="TRANSFER_OUT",
                batch_id=line.batch_id,
                serial_id=line.serial_id,
                reference_id=transfer.transfer_number,
            )
        )

    movements_out, consumptions = await consume_stock(session, costing_requests)
    
    # Process each movement (which corresponds 1:1 to the costing_requests / lines in order)
    for line, movement in zip(lines, movements_out, strict=True):
        movement_consumptions = [c for c in consumptions if c.movement_id == movement.id]
        
        total_qty = sum(c.qty_consumed for c in movement_consumptions)
        total_cost = sum(c.qty_consumed * c.unit_cost_at_consumption for c in movement_consumptions)
        
        if total_qty > 0:
            blended_unit_cost = total_cost / total_qty
        else:
            blended_unit_cost = Decimal("0")
            
        # Create inbound movement to transit warehouse
        transit_movement = StockMovement(
            item_id=line.item_id,
            variant_id=line.variant_id,
            warehouse_id=transfer.transit_warehouse_id,
            batch_id=line.batch_id,
            serial_id=line.serial_id,
            qty=line.qty_dispatched,
            movement_type="IN",
            reference_id=f"TRANSFER-TRANSIT-IN-{transfer.transfer_number}",
        )
        session.add(transit_movement)
        
        # Create inbound cost layer in transit warehouse
        transit_layer = CostLayer(
            item_id=line.item_id,
            variant_id=line.variant_id,
            warehouse_id=transfer.transit_warehouse_id,
            batch_id=line.batch_id,
            serial_id=line.serial_id,
            qty_received=line.qty_dispatched,
            qty_remaining=line.qty_dispatched,
            unit_cost_original=blended_unit_cost,
            unit_cost_current=blended_unit_cost,
        )
        session.add(transit_layer)
        
        # Update StockLevel in transit warehouse
        transit_level_stmt = (
            select(StockLevel)
            .where(
                StockLevel.item_id == line.item_id,
                StockLevel.variant_id == line.variant_id,
                StockLevel.warehouse_id == transfer.transit_warehouse_id,
                StockLevel.batch_id == line.batch_id,
                StockLevel.serial_id == line.serial_id,
            )
            .with_for_update()
        )
        transit_level = (await session.execute(transit_level_stmt)).scalar_one_or_none()
        
        if not transit_level:
            transit_level = StockLevel(
                item_id=line.item_id,
                variant_id=line.variant_id,
                warehouse_id=transfer.transit_warehouse_id,
                batch_id=line.batch_id,
                serial_id=line.serial_id,
                quantity=line.qty_dispatched,
            )
            session.add(transit_level)
        else:
            transit_level.quantity += line.qty_dispatched

    transfer.status = TransferStatus.IN_TRANSIT
    transfer.dispatched_at = datetime.now(UTC).replace(tzinfo=None)
    
    return transfer


async def receive_transfer(session: AsyncSession, transfer_id: UUID, receipt_lines: list[ReceiptLine]) -> StockTransfer:
    transfer = (await session.execute(
        select(StockTransfer).where(StockTransfer.id == transfer_id).with_for_update()
    )).scalar_one_or_none()

    if not transfer:
        raise ValueError(f"Transfer {transfer_id} not found")

    if transfer.status not in (TransferStatus.IN_TRANSIT, TransferStatus.PARTIALLY_RECEIVED):
        raise ValueError(f"Cannot receive transfer in status {transfer.status}")

    lines_query = (await session.execute(
        select(StockTransferLine).where(StockTransferLine.transfer_id == transfer_id).with_for_update()
    )).scalars().all()
    
    line_map = {line.id: line for line in lines_query}

    costing_requests = []
    receipts_to_process = []

    for receipt in receipt_lines:
        line = line_map.get(receipt.line_id)
        if not line:
            raise ValueError(f"Line {receipt.line_id} does not belong to transfer {transfer_id}")
            
        remaining_to_receive = line.qty_dispatched - line.qty_received
        if receipt.qty_received <= 0:
            raise ValueError(f"Invalid receipt quantity {receipt.qty_received} for line {line.id}")
            
        if receipt.qty_received > remaining_to_receive:
            raise ValueError(f"Cannot receive {receipt.qty_received}. Only {remaining_to_receive} remaining.")

        costing_requests.append(
            CostingRequest(
                item_id=line.item_id,
                variant_id=line.variant_id,
                warehouse_id=transfer.transit_warehouse_id,
                batch_id=line.batch_id,
                serial_id=line.serial_id,
                quantity=receipt.qty_received,
                movement_type="TRANSFER_OUT",
                reference_id=f"TRANSFER-TRANSIT-OUT-{transfer.transfer_number}",
            )
        )
        receipts_to_process.append((line, receipt.qty_received))

    if not costing_requests:
        return transfer

    movements_out, consumptions = await consume_stock(session, costing_requests)
    
    for (line, qty_received), movement in zip(receipts_to_process, movements_out, strict=True):
        movement_consumptions = [c for c in consumptions if c.movement_id == movement.id]
        
        total_qty = sum(c.qty_consumed for c in movement_consumptions)
        total_cost = sum(c.qty_consumed * c.unit_cost_at_consumption for c in movement_consumptions)
        
        if total_qty > 0:
            blended_unit_cost = total_cost / total_qty
        else:
            blended_unit_cost = Decimal("0")
            
        # Create inbound movement to destination warehouse
        dest_movement = StockMovement(
            item_id=line.item_id,
            variant_id=line.variant_id,
            warehouse_id=transfer.destination_warehouse_id,
            batch_id=line.batch_id,
            serial_id=line.serial_id,
            qty=qty_received,
            movement_type="IN",
            reference_id=f"TRANSFER-IN-{transfer.transfer_number}",
        )
        session.add(dest_movement)
        
        # Create inbound cost layer in destination warehouse
        dest_layer = CostLayer(
            item_id=line.item_id,
            variant_id=line.variant_id,
            warehouse_id=transfer.destination_warehouse_id,
            batch_id=line.batch_id,
            serial_id=line.serial_id,
            qty_received=qty_received,
            qty_remaining=qty_received,
            unit_cost_original=blended_unit_cost,
            unit_cost_current=blended_unit_cost,
        )
        session.add(dest_layer)
        
        # Update StockLevel in destination warehouse
        dest_level_stmt = (
            select(StockLevel)
            .where(
                StockLevel.item_id == line.item_id,
                StockLevel.variant_id == line.variant_id,
                StockLevel.warehouse_id == transfer.destination_warehouse_id,
                StockLevel.batch_id == line.batch_id,
                StockLevel.serial_id == line.serial_id,
            )
            .with_for_update()
        )
        dest_level = (await session.execute(dest_level_stmt)).scalar_one_or_none()
        
        if not dest_level:
            dest_level = StockLevel(
                item_id=line.item_id,
                variant_id=line.variant_id,
                warehouse_id=transfer.destination_warehouse_id,
                batch_id=line.batch_id,
                serial_id=line.serial_id,
                quantity=qty_received,
            )
            session.add(dest_level)
        else:
            dest_level.quantity += qty_received

        line.qty_received += qty_received

    # Determine new status based on whether all lines are fully received
    all_fully_received = all(line.qty_received == line.qty_dispatched for line in lines_query)
    
    if all_fully_received:
        transfer.status = TransferStatus.COMPLETED
    else:
        transfer.status = TransferStatus.PARTIALLY_RECEIVED
        
    transfer.received_at = datetime.now(UTC).replace(tzinfo=None)
    
    return transfer
