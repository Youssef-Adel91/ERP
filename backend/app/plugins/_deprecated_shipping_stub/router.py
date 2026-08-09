"""
DEPRECATED / DEAD — DO NOT REGISTER THIS ROUTER.

This was an early placeholder for shipping/carrier functionality before
that work was actually built. Real shipping is now implemented in
app.modules.logistics (carrier account config, waybill/shipment creation,
webhook ingestion with signature verification — see
app/modules/logistics/api/{carriers,shipments,webhooks}.py) and is
registered in app.main as step "11b. Shipping Plugin".

This directory was renamed from app/plugins/shipping to
app/plugins/_deprecated_shipping_stub and is not imported anywhere in the
app. Kept only for history; safe to delete entirely in a future cleanup.
"""
from fastapi import APIRouter

router = APIRouter()
