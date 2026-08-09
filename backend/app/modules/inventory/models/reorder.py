from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Column, Field, Numeric, SQLModel


class StockReorderRule(SQLModel, table=True):
    __tablename__ = "stock_reorder_rules"
    __table_args__ = {"schema": "tenant"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item_id: UUID = Field(index=True)
    warehouse_id: UUID = Field(index=True)
    reorder_point: Decimal = Field(
        sa_column=Column(Numeric(18, 4), nullable=False)
    )
    reorder_qty: Decimal = Field(
        sa_column=Column(Numeric(18, 4), nullable=False)
    )
