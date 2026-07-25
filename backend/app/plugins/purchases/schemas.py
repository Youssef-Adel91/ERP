
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field

from app.plugins.purchases.models import PurchaseInvoiceStatus


class PurchaseInvoiceLineCreateRequest(BaseModel):
    item_id: UUID
    quantity: Decimal = Field(gt=0, decimal_places=4)
    unit_price: Decimal = Field(ge=0, decimal_places=4)


class PurchaseInvoiceCreateRequest(BaseModel):
    supplier_id: UUID = Field(description="UUID of the supplier Contact record.")
    invoice_date: datetime = Field(default_factory=datetime.utcnow)
    lines: list[PurchaseInvoiceLineCreateRequest] = Field(min_length=1)


class PurchaseInvoiceLineResponse(BaseModel):
    id: UUID
    item_id: UUID
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class PurchaseInvoiceResponse(BaseModel):
    id: UUID
    supplier_id: UUID
    invoice_date: datetime
    total_amount: Decimal
    status: PurchaseInvoiceStatus
    created_at: datetime
    lines: list[PurchaseInvoiceLineResponse]

    model_config = {"from_attributes": True}
