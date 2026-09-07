import enum
from datetime import datetime, UTC
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Column, DateTime, Field, Numeric, SQLModel, text
import sqlalchemy as sa
from sqlalchemy import func


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
    # NOTE: must be explicitly schema-qualified via sa.Enum(..., schema="tenant"),
    # matching JournalEntryStatus/AccountType/ShiftStatus/etc. elsewhere in the
    # codebase. A bare `sa.Enum(StockTakeStatus)` here casts parameters as
    # unqualified `$N::stocktakestatus`, which does not resolve since the type
    # only exists inside each tenant schema (created by
    # f93809b48226_phase_1b_step_6_complete_inventory.py). create_type=False
    # because the enum type is already created by that migration.
    status: StockTakeStatus = Field(
        default=StockTakeStatus.DRAFT,
        sa_column=Column(
            sa.Enum(StockTakeStatus, name="stocktakestatus", schema="tenant", create_type=False),
            nullable=False,
        )
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
