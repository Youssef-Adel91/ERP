"""app/plugins/shipping/router.py — Shipping Plugin (Stub)

This plugin will handle shipment order management, carrier integration,
and COD delivery tracking in a future release.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/", tags=["Shipping"])
async def shipping_health() -> dict:
    return {"status": "shipping plugin — coming in next release"}
