
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from .models import SalesInvoiceStatus


class SalesInvoiceLineCreate(BaseModel):
    item_id: UUID
    quantity: Decimal = Field(gt=0, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, decimal_places=4)

class SalesInvoiceCreateRequest(BaseModel):
    customer_id: UUID
    notes: str | None = None
    lines: list[SalesInvoiceLineCreate] = Field(min_length=1)

class SalesInvoiceLineResponse(BaseModel):
    id: UUID
    item_id: UUID
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}

class SalesInvoiceResponse(BaseModel):
    id: UUID
    customer_id: UUID
    invoice_date: datetime
    total_amount: Decimal
    status: SalesInvoiceStatus
    created_at: datetime
    lines: list[SalesInvoiceLineResponse]

    model_config = {"from_attributes": True}
