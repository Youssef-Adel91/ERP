"""
app.modules.logistics.providers.registry — Carrier Provider Registry & Factory (FR-750)

Provides:
  1. get_carrier_provider(carrier_code): Factory returning corresponding CarrierProvider instance.
  2. list_supported_carriers(): Lists available carrier codes.
"""
from __future__ import annotations

from app.modules.logistics.providers.base import CarrierProvider
from app.modules.logistics.providers.bosta import BostaProvider
from app.modules.logistics.providers.mylerz import MylerzProvider

_PROVIDERS: dict[str, type[CarrierProvider]] = {
    "bosta": BostaProvider,
    "mylerz": MylerzProvider,
}


def get_carrier_provider(carrier_code: str) -> CarrierProvider:
    """
    Return an instance of CarrierProvider for the specified carrier_code.
    Raises ValueError if carrier_code is not supported.
    """
    code = carrier_code.lower().strip()
    provider_cls = _PROVIDERS.get(code)
    if not provider_cls:
        supported = ", ".join(sorted(_PROVIDERS.keys()))
        raise ValueError(
            f"Unsupported carrier code: '{carrier_code}'. Supported carriers: {supported}.",
        )
    return provider_cls()


def list_supported_carriers() -> list[str]:
    """Return list of supported carrier codes."""
    return sorted(_PROVIDERS.keys())
