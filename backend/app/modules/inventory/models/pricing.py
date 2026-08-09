from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Column, Field, Numeric, SQLModel, Date


class PriceList(SQLModel, table=True):
    __tablename__ = "price_lists"
    __table_args__ = {"schema": "tenant"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=255)
    currency: str = Field(max_length=3, default="EGP")
    valid_from: date | None = Field(default=None, sa_column=Column(Date))
    valid_to: date | None = Field(default=None, sa_column=Column(Date))


class PriceListRule(SQLModel, table=True):
    __tablename__ = "price_list_rules"
    __table_args__ = {"schema": "tenant"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    price_list_id: UUID = Field(index=True)
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    min_qty: Decimal = Field(
        default=Decimal("1.0"),
        sa_column=Column(Numeric(18, 4), nullable=False)
    )
    unit_price: Decimal = Field(
        sa_column=Column(Numeric(18, 4), nullable=False)
    )
