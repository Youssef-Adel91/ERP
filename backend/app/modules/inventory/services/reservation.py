from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.inventory.exceptions import InsufficientStockError
from app.modules.inventory.models.core import StockLevel, UnitOfMeasure


async def _get_base_qty(session: AsyncSession, qty: Decimal, uom_id: UUID | None) -> Decimal:
    if not uom_id:
        return qty
    stmt = select(UnitOfMeasure).where(UnitOfMeasure.id == uom_id)
    result = await session.execute(stmt)
    uom = result.scalar_one_or_none()
    if not uom:
        raise ValueError(f"UnitOfMeasure {uom_id} not found")
    return qty * uom.conversion_factor


async def reserve_stock(
    session: AsyncSession,
    item_id: UUID,
    warehouse_id: UUID,
    qty: Decimal,
    source_doc_id: str | None = None,
    variant_id: UUID | None = None,
    batch_id: UUID | None = None,
    serial_id: UUID | None = None,
    uom_id: UUID | None = None,
) -> bool:
    """
    Reserves stock for an order (FR-360).
    Acquires a row-level lock on StockLevel and increments qty_reserved
    if there is sufficient available stock.
    Raises InsufficientStockError if there is not enough stock.
    """
    if qty <= 0:
        raise ValueError("Reservation quantity must be strictly positive")

    base_qty = await _get_base_qty(session, qty, uom_id)

    stmt = (
        select(StockLevel)
        .where(
            StockLevel.item_id == item_id,
            StockLevel.variant_id == variant_id,
            StockLevel.warehouse_id == warehouse_id,
            StockLevel.batch_id == batch_id,
            StockLevel.serial_id == serial_id,
        )
        .with_for_update()
    )
    result = await session.execute(stmt)
    stock_level = result.scalar_one_or_none()

    qty_available = (stock_level.quantity - stock_level.qty_reserved) if stock_level else Decimal("0")
    if not stock_level or qty_available < base_qty:
        raise InsufficientStockError(
            f"Insufficient stock available for reservation: requested {base_qty}, available {qty_available}"
        )

    stock_level.qty_reserved += base_qty
    session.add(stock_level)
    return True


async def release_reservation(
    session: AsyncSession,
    item_id: UUID,
    warehouse_id: UUID,
    qty: Decimal,
    variant_id: UUID | None = None,
    batch_id: UUID | None = None,
    serial_id: UUID | None = None,
    uom_id: UUID | None = None,
):
    """
    Releases a prior reservation. Called on order cancellation or right
    before order fulfillment (so fulfillment drops both reserved and on_hand).
    """
    if qty <= 0:
        raise ValueError("Release quantity must be strictly positive")

    base_qty = await _get_base_qty(session, qty, uom_id)

    stmt = (
        select(StockLevel)
        .where(
            StockLevel.item_id == item_id,
            StockLevel.variant_id == variant_id,
            StockLevel.warehouse_id == warehouse_id,
            StockLevel.batch_id == batch_id,
            StockLevel.serial_id == serial_id,
        )
        .with_for_update()
    )
    result = await session.execute(stmt)
    stock_level = result.scalar_one_or_none()

    if not stock_level:
        raise ValueError("Cannot release reservation for non-existent stock level")

    if stock_level.qty_reserved < base_qty:
        # Self-correcting for safety
        stock_level.qty_reserved = Decimal("0")
    else:
        stock_level.qty_reserved -= base_qty

    session.add(stock_level)
