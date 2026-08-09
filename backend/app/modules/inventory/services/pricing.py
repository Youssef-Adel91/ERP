from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.inventory.models.core import ItemVariant, UnitOfMeasure
from app.modules.inventory.models.pricing import PriceListRule


async def get_item_price(
    session: AsyncSession,
    item_id: UUID,
    price_list_id: UUID | None = None,
    variant_id: UUID | None = None,
    qty: Decimal = Decimal("1.0"),
    uom_id: UUID | None = None,
) -> Decimal:
    """
    Fetches the unit price for an item (or variant), taking into account:
    - Active price list and quantity breaks (min_qty in base units).
    - UnitOfMeasure conversion factor (returns price per requested UoM).
    - Fallback to ItemVariant.price if no PriceListRule matches.
    - Fallback to 0.0 if no variant price exists.
    """
    cf = Decimal("1.0")
    if uom_id:
        uom_stmt = select(UnitOfMeasure).where(UnitOfMeasure.id == uom_id)
        uom_res = await session.execute(uom_stmt)
        uom = uom_res.scalar_one_or_none()
        if uom:
            cf = uom.conversion_factor

    base_qty = qty * cf
    base_price: Decimal | None = None

    if price_list_id:
        rule_stmt = (
            select(PriceListRule)
            .where(
                PriceListRule.price_list_id == price_list_id,
                PriceListRule.item_id == item_id,
                (PriceListRule.variant_id == variant_id) | (PriceListRule.variant_id.is_(None)),  # type: ignore[attr-defined]
                PriceListRule.min_qty <= base_qty,
            )
            .order_by(PriceListRule.min_qty.desc())
        )
        rule_res = await session.execute(rule_stmt)
        rule = rule_res.scalars().first()
        if rule:
            base_price = rule.unit_price

    if base_price is None and variant_id:
        var_stmt = select(ItemVariant).where(ItemVariant.id == variant_id)
        var_res = await session.execute(var_stmt)
        variant = var_res.scalar_one_or_none()
        if variant:
            base_price = variant.price

    if base_price is None:
        base_price = Decimal("0.0")

    return base_price * cf
