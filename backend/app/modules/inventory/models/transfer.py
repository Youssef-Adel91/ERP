from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, Numeric, text
from sqlmodel import Field, SQLModel


class TransferStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_TRANSIT = "IN_TRANSIT"
    COMPLETED = "COMPLETED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"


class StockTransfer(SQLModel, table=True):
    __tablename__ = "stock_transfers"
    __table_args__ = (
        CheckConstraint(
            "source_warehouse_id != destination_warehouse_id AND "
            "source_warehouse_id != transit_warehouse_id AND "
            "destination_warehouse_id != transit_warehouse_id",
            name="ck_transfers_distinct_warehouses"
        ),
        {"schema": "tenant"}
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    transfer_number: str = Field(max_length=50, index=True, unique=True)
    
    source_warehouse_id: UUID = Field(index=True)
    destination_warehouse_id: UUID = Field(index=True)
    transit_warehouse_id: UUID = Field(index=True)
    
    # NOTE: must be explicitly schema-qualified via sa.Enum(..., schema="tenant"),
    # matching JournalEntryStatus/AccountType/ShiftStatus/etc. elsewhere in the
    # codebase. A bare `sa.Enum(TransferStatus)` here casts parameters as
    # unqualified `$N::transferstatus`, which does not resolve since the type
    # only exists inside each tenant schema (created by
    # f93809b48226_phase_1b_step_6_complete_inventory.py). create_type=False
    # because the enum type is already created by that migration.
    status: TransferStatus = Field(
        default=TransferStatus.DRAFT,
        sa_column=Column(
            sa.Enum(TransferStatus, name="transferstatus", schema="tenant", create_type=False),
            nullable=False,
            index=True,
        ),
    )
    
    dispatched_at: datetime | None = Field(default=None)
    received_at: datetime | None = Field(default=None)
    
    created_by: UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )


class StockTransferLine(SQLModel, table=True):
    __tablename__ = "stock_transfer_lines"
    __table_args__ = (
        CheckConstraint("qty_dispatched > 0", name="ck_transfer_lines_qty_dispatched"),
        CheckConstraint("qty_received >= 0", name="ck_transfer_lines_qty_received"),
        {"schema": "tenant"}
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    transfer_id: UUID = Field(index=True)
    
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    batch_id: UUID | None = Field(default=None, index=True)
    serial_id: UUID | None = Field(default=None, index=True)
    
    qty_dispatched: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    qty_received: Decimal = Field(
        default=Decimal("0.0"), 
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0"))
    )
