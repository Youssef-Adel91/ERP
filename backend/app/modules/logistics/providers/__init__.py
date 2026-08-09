"""
app.modules.logistics.providers — Carrier Provider Plugins & Factory
"""
from app.modules.logistics.providers.base import (
    CarrierProvider,
    ShipmentCreationResult,
    WebhookParseResult,
)
from app.modules.logistics.providers.bosta import BostaProvider
from app.modules.logistics.providers.mylerz import MylerzProvider
from app.modules.logistics.providers.registry import (
    get_carrier_provider,
    list_supported_carriers,
)

__all__ = [
    "BostaProvider",
    "CarrierProvider",
    "MylerzProvider",
    "ShipmentCreationResult",
    "WebhookParseResult",
    "get_carrier_provider",
    "list_supported_carriers",
]
