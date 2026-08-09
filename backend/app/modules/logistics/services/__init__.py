"""
app.modules.logistics.services — Logistics Business Services (Phase 7b)
"""
from app.modules.logistics.services.shipments import (
    create_shipment,
    process_shipment_webhook_payload,
    record_physical_return_receipt,
    update_shipment_status,
)
from app.modules.logistics.services.webhooks import ingest_carrier_webhook

__all__ = [
    "create_shipment",
    "ingest_carrier_webhook",
    "process_shipment_webhook_payload",
    "record_physical_return_receipt",
    "update_shipment_status",
]
