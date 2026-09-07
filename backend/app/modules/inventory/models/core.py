from datetime import UTC, datetime
from decimal import Decimal
from datetime import date
from enum import StrEnum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, Numeric, String, UniqueConstraint, text, Date
from sqlmodel import Field, SQLModel


class CostingMethod(StrEnum):
    FIFO = "FIFO"
    WAC = "WAC"
    LIFO = "LIFO"
    STANDARD = "STANDARD"


class WarehouseType(StrEnum):
    MAIN = "MAIN"
    RETAIL = "RETAIL"
    TRANSIT = "TRANSIT"
    QUARANTINE = "QUARANTINE"
    DAMAGED = "DAMAGED"
    CONSIGNMENT = "CONSIGNMENT"


class SerialState(StrEnum):
    IN_STOCK = "IN_STOCK"
    RESERVED = "RESERVED"
    SOLD = "SOLD"
    RETURNED = "RETURNED"
    SCRAPPED = "SCRAPPED"
    UNDER_REPAIR = "UNDER_REPAIR"


class BatchStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    QUARANTINED = "QUARANTINED"
    RECALLED = "RECALLED"


class Warehouse(SQLModel, table=True):
    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("code", name="uq_warehouses_code"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=255)
    code: str = Field(max_length=50, index=True)
    # NOTE: must be explicitly schema-qualified via sa.Enum(..., schema="tenant"),
    # matching JournalEntryStatus/AccountType/ShiftStatus/etc. elsewhere in the
    # codebase. Without an explicit schema= here, SQLModel auto-infers a bare
    # `sa.Enum(WarehouseType)` with no schema, so generated SQL casts parameters
    # as unqualified `$N::warehousetype` — which only resolves if "warehousetype"
    # happens to be on the connection's search_path, which it is not. That
    # produced `asyncpg.exceptions.UndefinedObjectError: type "warehousetype"
    # does not exist` even though the type exists (correctly) inside each
    # tenant schema, created by f93809b48226_phase_1b_step_6_complete_inventory.py.
    # create_type=False because the enum type is already created by that
    # migration; SQLAlchemy/Alembic must never try to CREATE TYPE it again.
    type: WarehouseType = Field(
        default=WarehouseType.MAIN,
        sa_column=Column(
            sa.Enum(WarehouseType, name="warehousetype", schema="tenant", create_type=False),
            nullable=False,
        ),
    )


class Item(SQLModel, table=True):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_items_sku"),
        {"schema": "tenant", "extend_existing": True},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sku: str = Field(max_length=100, index=True)
    name: str = Field(max_length=255)
    egs_code: str | None = Field(default=None, max_length=100, index=True)
    # NOTE: stored as a plain VARCHAR (matches the actual column created by
    # every migration in the tenant chain — see f93809b48226's add_column
    # for `costing_method`). Without this explicit sa_column, SQLModel would
    # infer sa.Enum(CostingMethod) from the Python StrEnum, which requires a
    # native Postgres enum TYPE called "costingmethod" that no migration
    # ever created — causing every insert/select to fail with
    # `type "costingmethod" does not exist`. String + StrEnum round-trips
    # correctly since CostingMethod values ARE plain strings.
    costing_method: CostingMethod = Field(
        default=CostingMethod.FIFO,
        sa_column=Column(String(20), nullable=True),
    )
    
    requires_batch: bool = Field(default=False)
    requires_serial: bool = Field(default=False)


class ItemVariant(SQLModel, table=True):
    __tablename__ = "item_variants"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_item_variants_sku"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item_id: UUID = Field(index=True)
    name: str = Field(max_length=255)
    sku: str = Field(max_length=100, index=True)
    price: Decimal = Field(
        default=Decimal("0.0"), 
        sa_column=Column(Numeric(18, 4), nullable=False)
    )
    
    requires_batch: bool = Field(default=False)
    requires_serial: bool = Field(default=False)


class ItemBarcode(SQLModel, table=True):
    __tablename__ = "item_barcodes"
    __table_args__ = (
        UniqueConstraint("barcode", name="uq_item_barcodes_barcode"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    uom_id: UUID | None = Field(default=None, index=True)
    barcode: str = Field(max_length=100, index=True)


class UnitOfMeasure(SQLModel, table=True):
    __tablename__ = "uoms"
    __table_args__ = ({"schema": "tenant"},)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item_id: UUID = Field(index=True)
    name: str = Field(max_length=50)
    conversion_factor: Decimal = Field(
        sa_column=Column(Numeric(18, 6), nullable=False, server_default=text("1.0"))
    )
    is_base: bool = Field(default=False)


class Batch(SQLModel, table=True):
    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("item_id", "batch_no", name="uq_batches_item_batch"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    batch_no: str = Field(max_length=100, index=True)
    
    manufacture_date: date | None = Field(default=None, sa_column=Column(Date))
    expiry_date: date | None = Field(default=None, sa_column=Column(Date))
    # See NOTE on Warehouse.type above — same missing-schema bug. Enum type
    # "batchstatus" is created inside the tenant schema by
    # f93809b48226_phase_1b_step_6_complete_inventory.py.
    status: BatchStatus = Field(
        default=BatchStatus.ACTIVE,
        sa_column=Column(
            sa.Enum(BatchStatus, name="batchstatus", schema="tenant", create_type=False),
            nullable=False,
        ),
    )


class SerialNumber(SQLModel, table=True):
    __tablename__ = "serial_numbers"
    __table_args__ = (
        UniqueConstraint("item_id", "serial_no", name="uq_serial_numbers_item_serial"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    serial_no: str = Field(max_length=100, index=True)
    
    # See NOTE on Warehouse.type above — same missing-schema bug. Enum type
    # "serialstate" is created inside the tenant schema by
    # f93809b48226_phase_1b_step_6_complete_inventory.py.
    state: SerialState = Field(
        default=SerialState.IN_STOCK,
        sa_column=Column(
            sa.Enum(SerialState, name="serialstate", schema="tenant", create_type=False),
            nullable=False,
        ),
    )
    warehouse_id: UUID | None = Field(default=None, index=True)
    current_owner_contact_id: UUID | None = Field(default=None, index=True)


class StockLevel(SQLModel, table=True):
    """
    Transactional cache for quick stock read and concurrency locks (FR-333).
    Granularity is (item, variant, warehouse).
    """

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint(
            "item_id", "variant_id", "warehouse_id", "batch_id", "serial_id", name="uq_stock_levels_granularity"
        ),
        CheckConstraint("quantity >= 0", name="ck_stock_levels_non_negative"),
        CheckConstraint("serial_id IS NULL OR quantity <= 1", name="ck_stock_levels_serial_qty_is_one"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    warehouse_id: UUID = Field(index=True)
    batch_id: UUID | None = Field(default=None, index=True)
    serial_id: UUID | None = Field(default=None, index=True)

    quantity: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )
    qty_reserved: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )


class CostLayer(SQLModel, table=True):
    """
    Exact mapping to Step 1 DDL. Lineage preservation.
    """

    __tablename__ = "cost_layers"
    __table_args__ = (
        CheckConstraint("qty_received >= 0", name="ck_cost_layers_received"),
        CheckConstraint("qty_remaining >= 0", name="ck_cost_layers_remaining"),
        CheckConstraint("serial_id IS NULL OR qty_received = 1", name="ck_cost_layers_serial_layer_qty_is_one"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    warehouse_id: UUID = Field(index=True)
    batch_id: UUID | None = Field(default=None, index=True)
    serial_id: UUID | None = Field(default=None, index=True)

    qty_received: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    qty_remaining: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))

    unit_cost_original: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    unit_cost_current: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    landed_cost_applied: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )

    is_provisional: bool = Field(default=False)

    received_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )
    sequence_no: int = Field(default=1)


class StockMovement(SQLModel, table=True):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("serial_id IS NULL OR qty = 1 OR qty = -1", name="ck_stock_movements_serial_qty_is_one"),
        {"schema": "tenant"}
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    warehouse_id: UUID = Field(index=True)
    batch_id: UUID | None = Field(default=None, index=True)
    serial_id: UUID | None = Field(default=None, index=True)

    qty: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    movement_type: str = Field(max_length=50)  # 'IN' or 'OUT' or 'ADJUST'
    reference_id: str | None = Field(default=None, max_length=255)
    contact_id: UUID | None = Field(default=None, index=True)
    
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        index=True
    )
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )


class CostConsumption(SQLModel, table=True):
    """
    Mapping between a consumption layer and an outbound stock movement.
    """

    __tablename__ = "cost_consumptions"
    __table_args__ = ({"schema": "tenant"},)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    layer_id: UUID = Field(index=True)
    movement_id: UUID = Field(index=True)

    qty_consumed: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    unit_cost_at_consumption: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    
    adjustment_of_id: UUID | None = Field(default=None, index=True)
    adjustment_reason: str | None = Field(default=None, max_length=255)
