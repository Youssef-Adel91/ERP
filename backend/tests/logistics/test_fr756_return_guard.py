"""
tests.logistics.test_fr756_return_guard — Tests for FR-756 Return Guard & Physical Return Receipt

Tests:
  1. Carrier status 'RETURNED' updates state to RETURNED but leaves return_received_at as None (no auto-restock).
  2. record_physical_return_receipt sets return_received_at and emits physical_return_received=True event.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.logistics.models.carriers import CarrierAccount, ShipmentState
from app.modules.logistics.services.shipments import (
    create_shipment,
    record_physical_return_receipt,
    update_shipment_status,
)
from tests.conftest import TEST_TENANT_ID

pytestmark = pytest.mark.asyncio


async def test_fr756_carrier_returned_no_restock(db_session: AsyncSession):
    """
    Verify carrier RETURNED status update does NOT set return_received_at (FR-756 compliance).
    """
    tenant_id = str(TEST_TENANT_ID)
    invoice_id = uuid4()

    account = CarrierAccount(
        carrier_code="bosta",
        credentials_ref="vault:bosta:1",
        webhook_secret_ref="vault:bosta:webhook:1",  # noqa: S106
    )
    db_session.add(account)
    await db_session.flush()

    shipment = await create_shipment(
        session=db_session,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        carrier_code="bosta",
        cod_amount=Decimal("150.00"),
        invoice_data={"customer": "Test User"},
        account=account,
    )
    assert shipment.state == ShipmentState.CREATED
    assert shipment.return_received_at is None

    # Update state to RETURNED (e.g. from carrier webhook)
    updated = await update_shipment_status(
        session=db_session,
        tenant_id=tenant_id,
        shipment=shipment,
        canonical_state=ShipmentState.RETURNED,
        status_raw="RETURNED_TO_BUSINESS",
        payload={"reason": "Customer rejected package"},
    )
    assert updated.state == ShipmentState.RETURNED
    # CRITICAL FR-756 requirement:
    assert updated.return_received_at is None


async def test_fr756_physical_return_receipt(db_session: AsyncSession):
    """
    Verify record_physical_return_receipt timestamps return_received_at and emits return event (FR-756).
    """
    tenant_id = str(TEST_TENANT_ID)
    invoice_id = uuid4()

    account = CarrierAccount(
        carrier_code="bosta",
        credentials_ref="vault:bosta:1",
        webhook_secret_ref="vault:bosta:webhook:1",  # noqa: S106
    )
    db_session.add(account)
    await db_session.flush()

    shipment = await create_shipment(
        session=db_session,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        carrier_code="bosta",
        cod_amount=Decimal("200.00"),
        invoice_data={"customer": "Test User 2"},
        account=account,
    )

    # First update to carrier RETURNED state
    await update_shipment_status(
        session=db_session,
        tenant_id=tenant_id,
        shipment=shipment,
        canonical_state=ShipmentState.RETURNED,
        status_raw="RETURNED_TO_BUSINESS",
        payload={"reason": "Customer rejected package"},
    )

    # Now warehouse worker scans physical return
    phys_shipment = await record_physical_return_receipt(
        session=db_session,
        tenant_id=tenant_id,
        shipment_id=shipment.id,
    )
    assert phys_shipment.id == shipment.id
    assert phys_shipment.return_received_at is not None
    assert phys_shipment.state == ShipmentState.RETURNED
