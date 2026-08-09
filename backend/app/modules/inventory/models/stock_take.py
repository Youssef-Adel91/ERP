import enum
from datetime import datetime, UTC
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Column, DateTime, Field, Numeric, SQLModel, text
from sqlalchemy import Enum, func


class StockTakeStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    COUNTING = "COUNTING"
    REVIEW = "REVIEW"
    POSTED = "POSTED"


class StockTake(SQLModel, table=True):
    __tablename__ = "stock_takes"
    __table_args__ = {"schema": "tenant"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    warehouse_id: UUID = Field(index=True)
    status: StockTakeStatus = Field(
        default=StockTakeStatus.DRAFT,
        sa_column=Column(Enum(StockTakeStatus), nullable=False)
    )
    reference_id: str | None = Field(default=None, max_length=100)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )


class StockTakeLine(SQLModel, table=True):
    __tablename__ = "stock_take_lines"
    __table_args__ = {"schema": "tenant"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    stock_take_id: UUID = Field(index=True)
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    batch_id: UUID | None = Field(default=None, index=True)
    serial_id: UUID | None = Field(default=None, index=True)

    expected_qty: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )
    counted_qty: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 4), nullable=True),
    )
    variance_qty: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 4), nullable=True),
    )
    unit_cost: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 4), nullable=True),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )
