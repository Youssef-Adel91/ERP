"""
app.modules.logistics.api.shipments — Shipment Creation & Tracking (FR-750, FR-756)

Exposes the "شحن" (Ship) action: turns a POSTED Sales Invoice into a
carrier waybill via app.modules.logistics.services.shipments.create_shipment,
using the tenant's own configured CarrierAccount (app.modules.logistics.
api.carriers). Route order: POST /shipments and GET /shipments (list) come
before GET/POST /shipments/{shipment_id}... so literal-vs-dynamic path
collision isn't a concern here (no literal sibling under {shipment_id}),
but /shipments/{shipment_id}/cancel still needs {shipment_id} resolved as
a path param, which FastAPI handles fine since there's no separate
"/shipments/cancel" literal route to collide with.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.db.database import get_tenant_db
from app.modules.contacts.models import Contact
from app.modules.logistics.models.carriers import CarrierAccount, Shipment, ShipmentState
from app.modules.logistics.providers.registry import get_carrier_provider
from app.modules.logistics.services.shipments import create_shipment, update_shipment_status
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/logistics/shipments", tags=["Logistics — Shipments"])


class ShipmentCreateIn(BaseModel):
    invoice_id: UUID
    carrier_code: str
    cod_amount: Decimal = Decimal("0")
    dropoff_address: str | None = None


@router.get("", response_model=list[Shipment])
async def list_shipments(
    current_user: CurrentUser,
    invoice_id: UUID | None = None,
    db=Depends(get_tenant_db),
):
    stmt = select(Shipment)
    if invoice_id:
        stmt = stmt.where(Shipment.invoice_id == invoice_id)
    stmt = stmt.order_by(Shipment.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=Shipment, status_code=status.HTTP_201_CREATED)
async def ship_invoice(
    data: ShipmentCreateIn,
    current_user: CurrentUser,
    db=Depends(get_tenant_db),
):
    invoice = await db.get(SalesInvoice, data.invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="فاتورة البيع غير موجودة.")
    if invoice.status != SalesInvoiceStatus.POSTED and invoice.status != SalesInvoiceStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="لازم ترحيل الفاتورة أولًا قبل إنشاء شحنة لها.",
        )

    existing = await db.execute(
        select(Shipment).where(
            Shipment.invoice_id == invoice.id,
            Shipment.state != ShipmentState.CANCELLED,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="يوجد بالفعل شحنة نشطة لهذه الفاتورة.",
        )

    code = data.carrier_code.lower().strip()
    account_result = await db.execute(
        select(CarrierAccount).where(
            CarrierAccount.carrier_code == code,
            CarrierAccount.is_active == True,  # noqa: E712
        )
    )
    account = account_result.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"لا يوجد حساب مُفعّل لشركة الشحن '{data.carrier_code}'. من فضلك اضبطه أولًا من إعدادات الشحن.",
        )

    contact = await db.get(Contact, invoice.contact_id)

    invoice_data: dict[str, Any] = {
        "invoice_number": invoice.invoice_number,
        "grand_total": str(invoice.grand_total),
        "customer_name": contact.name if contact else "",
        "customer_phone": (contact.phone_e164 or contact.phone) if contact else "",
        "dropoff_address": data.dropoff_address or "",
    }

    try:
        shipment = await create_shipment(
            session=db,
            tenant_id=str(current_user.tenant_id),
            invoice_id=invoice.id,
            carrier_code=code,
            cod_amount=data.cod_amount,
            invoice_data=invoice_data,
            account=account,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await db.commit()
    await db.refresh(shipment)
    return shipment


@router.post("/{shipment_id}/cancel", response_model=Shipment)
async def cancel_shipment(
    shipment_id: UUID,
    current_user: CurrentUser,
    db=Depends(get_tenant_db),
):
    shipment = await db.get(Shipment, shipment_id)
    if not shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="الشحنة غير موجودة.")
    if shipment.state == ShipmentState.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="الشحنة ملغاة بالفعل.")
    if shipment.state in (ShipmentState.DELIVERED, ShipmentState.RETURNED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="لا يمكن إلغاء شحنة تم تسليمها أو إرجاعها بالفعل.")

    account_result = await db.execute(
        select(CarrierAccount).where(CarrierAccount.carrier_code == shipment.carrier_code)
    )
    account = account_result.scalar_one_or_none()
    if account:
        provider = get_carrier_provider(shipment.carrier_code)
        await provider.cancel_shipment(awb_number=shipment.awb_number, account=account)

    shipment = await update_shipment_status(
        session=db,
        tenant_id=str(current_user.tenant_id),
        shipment=shipment,
        canonical_state=ShipmentState.CANCELLED,
        status_raw="CANCELLED_BY_MERCHANT",
        payload={"cancelled_by_user_id": str(current_user.id)},
    )
    await db.commit()
    await db.refresh(shipment)
    return shipment
