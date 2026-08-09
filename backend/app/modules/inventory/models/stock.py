"""
app/modules/inventory/models/stock.py — Stock Domain Models

RESOLUTION RECORD (Phase 1 dedup, see models/core.py): this file defined a
duplicate ProductBatch/CostLayer pair (tables inv_product_batches /
inv_cost_layers) separate from the canonical Batch/CostLayer pair in
models/core.py (tables batches / cost_layers), which is tied into
Item/Warehouse/ItemVariant/StockLevel/StockMovement/CostConsumption and is
what services/costing.py's consume_stock() actually uses. models/core.py's
pair was kept as the single source of truth; api/stock.py and
services/costing.py's consume_stock_fifo() were migrated off of this file's
ProductBatch/CostLayer onto models/core.py's Batch/CostLayer. Nothing in the
codebase imports from this module anymore as of that migration. The classes
below are left in place (unused, not exported from models/__init__.py) rather
than deleted, so this decision is reversible without digging through git
history — feel free to delete this file once the migration has baked in.
"""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Column, Date, DateTime, Index, Numeric
from sqlmodel import Field

from app.core.db.base import TenantBase


class ProductBatch(TenantBase, table=True):
    __tablename__ = "inv_product_batches"
    __table_args__ = {"schema": "tenant"}

    product_id: UUID = Field(index=True)
    batch_number: str = Field(max_length=100, index=True)
    manufacturing_date: date | None = Field(default=None, sa_column=Column(Date))
    expiry_date: date | None = Field(default=None, sa_column=Column(Date))


class CostLayer(TenantBase, table=True):
    __tablename__ = "inv_cost_layers"
    __table_args__ = (
        Index("ix_inv_cost_layers_fifo", "product_id", "warehouse_id", "received_at"),
        {"schema": "tenant"},
    )

    product_id: UUID = Field(index=True)
    batch_id: UUID | None = Field(default=None, index=True)
    warehouse_id: UUID = Field(index=True)
    
    received_qty: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    remaining_qty: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    unit_cost: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    
    received_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
