from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.inventory.models.core import Item, StockLevel, Warehouse
from app.modules.inventory.models.reorder import StockReorderRule
from app.core.reports.decorators import reporting_tool

@reporting_tool(
    name="Needs Reordering Report",
    description_ar="تقرير النواقص وإعادة الطلب",
    required_permission="reports.inventory.reorder",
)
async def get_needs_reordering_report(session: AsyncSession) -> list[dict]:
    """
    Returns actionable list of items requiring reordering across all warehouses.
    """
    stmt = (
        select(
            StockReorderRule.warehouse_id,
            Warehouse.name.label("warehouse_name"),
            StockReorderRule.item_id,
            Item.sku,
            Item.name.label("item_name"),
            StockLevel.quantity,
            StockLevel.qty_reserved,
            StockReorderRule.reorder_point,
            StockReorderRule.reorder_qty,
        )
        .select_from(StockReorderRule)
        .join(Item, Item.id == StockReorderRule.item_id)
        .join(Warehouse, Warehouse.id == StockReorderRule.warehouse_id)
        .outerjoin(
            StockLevel,
            (StockLevel.item_id == StockReorderRule.item_id)
            & (StockLevel.warehouse_id == StockReorderRule.warehouse_id)
        )
    )

    result = await session.execute(stmt)
    rows = result.all()

    report = []
    for row in rows:
        available = (row.quantity or 0) - (row.qty_reserved or 0)
        if available <= row.reorder_point:
            report.append({
                "warehouse_id": str(row.warehouse_id),
                "warehouse_name": row.warehouse_name,
                "item_id": str(row.item_id),
                "sku": row.sku,
                "item_name": row.item_name,
                "available_qty": float(available),
                "reorder_point": float(row.reorder_point),
                "suggested_reorder_qty": float(row.reorder_qty),
            })
            
    return report
