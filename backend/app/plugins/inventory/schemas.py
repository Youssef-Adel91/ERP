"""
app/plugins/inventory/schemas.py — Inventory Plugin Pydantic Schemas
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.plugins.inventory.models import InvoiceStatus


# ── Item ──────────────────────────────────────────────────────────────────────


class ItemCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    name_ar: str | None = Field(default=None, max_length=255)
    sku: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=100)
    price: Decimal = Field(ge=0, decimal_places=4)
    cost: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=4)
    initial_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)


class ItemResponse(BaseModel):
    id: UUID
    name: str
    name_ar: str | None
    sku: str
    category: str | None
    price: Decimal
    cost: Decimal
    quantity_on_hand: Decimal
    reorder_level: Decimal
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Invoice ───────────────────────────────────────────────────────────────────


class InvoiceLineCreateRequest(BaseModel):
    item_id: UUID
    quantity: Decimal = Field(gt=0, decimal_places=4)
    unit_price: Decimal | None = Field(
        default=None,
        ge=0,
        description="If omitted, uses the item's current price.",
    )


class InvoiceCreateRequest(BaseModel):
    contact_id: UUID = Field(description="UUID of the customer Contact record.")
    lines: list[InvoiceLineCreateRequest] = Field(
        min_length=1,
        description="At least one line item is required.",
    )
    notes: str | None = Field(default=None, max_length=2000)

    # Accounting accounts — used in EventBus payload for journal entry creation
    ar_account_code: str = Field(
        default="1200",
        description="Accounts Receivable account code (default: '1200').",
    )
    revenue_account_code: str = Field(
        default="4010",
        description="Sales Revenue account code (default: '4010').",
    )


class InvoiceLineResponse(BaseModel):
    id: UUID
    item_id: UUID
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: UUID
    invoice_number: str
    contact_id: UUID
    status: InvoiceStatus
    total_amount: Decimal
    notes: str | None
    lines: list[InvoiceLineResponse]
    created_at: datetime

    model_config = {"from_attributes": True}
