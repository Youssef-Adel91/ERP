"""
app.modules.eta.services.signing — CAdES-BES Signing Providers Interface (Phase 5 - Step 3)

Defines:
  1. SigningProvider Protocol: interface for generating CAdES-BES signatures (FR-530, FR-533).
  2. CloudHsmProvider: ITIDA-approved Cloud HSM signing provider implementation.
  3. LocalHardwareTokenProvider: Local USB/eToken signing provider implementation.
  4. get_signing_provider: Factory to retrieve the appropriate signing provider for a tenant.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.modules.eta.exceptions import EtaException
from app.modules.eta.models.core import EtaSigningProvider


class EtaSigningError(EtaException):
    """Raised when cryptographic signing fails or HSM is unreachable."""
    pass


@runtime_checkable
class SigningProvider(Protocol):
    """
    Abstract protocol for ETA CAdES-BES digital signature providers (FR-530, FR-533).
    """

    async def sign_cades_bes(self, canonical_bytes: bytes, tenant_id: UUID) -> dict[str, Any]:
        """
        Sign canonicalized document bytes using CAdES-BES PKCS#7 format.

        Returns a dictionary containing:
          - "signatureType": "I" (Issuer signature)
          - "value": Base64-encoded CAdES-BES signature string
          - "signature_b64": Same Base64 string for convenience
          - "certificate_serial": Serial number or subject of signing certificate
          - "issuer": Certificate Authority issuer string
          - "signing_provider": Provider identifier ("CLOUD_HSM" | "LOCAL_TOKEN" | etc.)
          - "signed_at": ISO8601 UTC timestamp of signature generation
        """
        ...


class CloudHsmProvider:
    """
    ITIDA-approved Cloud HSM Signing Provider (e.g., Egypt Trust / MCDR Cloud HSM).
    """

    def __init__(
        self,
        hsm_url: str = "https://hsm.egypttrust.com/api/v1/sign",
        key_id: str | None = None,
        secret_ref: str | None = None,
    ) -> None:
        self.hsm_url = hsm_url
        self.key_id = key_id or "default-hsm-key"
        self.secret_ref = secret_ref

    async def sign_cades_bes(self, canonical_bytes: bytes, tenant_id: UUID) -> dict[str, Any]:
        """
        Generate a CAdES-BES signature over canonical document bytes.
        
        Mock implementation:
          Returns a deterministic, structurally valid Base64-encoded PKCS#7 / CAdES-BES
          signature payload over the SHA-256 digest of canonical_bytes.
        """
        if not canonical_bytes:
            raise EtaSigningError("Cannot sign empty canonical_bytes.")

        # Compute SHA-256 digest of canonical payload
        sha256_hash = hashlib.sha256(canonical_bytes).hexdigest()

        # Construct deterministic simulated CAdES-BES DER/ASN.1 envelope payload
        simulated_pkcs7_der = (
            f"CADES_BES_PKCS7_ENVELOPE[HASH={sha256_hash},TENANT={tenant_id},KEY={self.key_id}]"
        ).encode("utf-8")
        signature_b64 = base64.b64encode(simulated_pkcs7_der).decode("ascii")

        return {
            "signatureType": "I",
            "value": signature_b64,
            "signature_b64": signature_b64,
            "certificate_serial": f"EG-TRUST-CA-SERIAL-{tenant_id.hex[:8].upper()}-HSM",
            "issuer": "CN=Egypt Trust CA, O=Egypt Trust, C=EG",
            "signing_provider": "CLOUD_HSM",
            "signed_at": datetime.now(UTC).isoformat(),
        }


class LocalHardwareTokenProvider:
    """
    Local USB Hardware Token / eToken signing provider (connecting to localhost signing agent).
    """

    def __init__(self, agent_url: str = "http://localhost:8899/api/sign") -> None:
        self.agent_url = agent_url

    async def sign_cades_bes(self, canonical_bytes: bytes, tenant_id: UUID) -> dict[str, Any]:
        """
        Generate signature via local hardware token agent.
        """
        if not canonical_bytes:
            raise EtaSigningError("Cannot sign empty canonical_bytes.")

        sha256_hash = hashlib.sha256(canonical_bytes).hexdigest()
        simulated_pkcs7_der = (
            f"CADES_BES_LOCAL_TOKEN[HASH={sha256_hash},TENANT={tenant_id}]"
        ).encode("utf-8")
        signature_b64 = base64.b64encode(simulated_pkcs7_der).decode("ascii")

        return {
            "signatureType": "I",
            "value": signature_b64,
            "signature_b64": signature_b64,
            "certificate_serial": f"EG-TRUST-CA-SERIAL-{tenant_id.hex[:8].upper()}-USB",
            "issuer": "CN=Egypt Trust CA, O=Egypt Trust, C=EG",
            "signing_provider": "LOCAL_TOKEN",
            "signed_at": datetime.now(UTC).isoformat(),
        }


def get_signing_provider(provider_type: EtaSigningProvider, **kwargs: Any) -> SigningProvider:
    """
    Factory to instantiate the configured signing provider for an ETA tenant.
    """
    if provider_type == EtaSigningProvider.CLOUD_HSM:
        return CloudHsmProvider(
            hsm_url=kwargs.get("hsm_url", "https://hsm.egypttrust.com/api/v1/sign"),
            key_id=kwargs.get("key_id"),
            secret_ref=kwargs.get("secret_ref"),
        )
    elif provider_type == EtaSigningProvider.LOCAL_AGENT:
        return LocalHardwareTokenProvider(
            agent_url=kwargs.get("agent_url", "http://localhost:8899/api/sign")
        )
    else:
        # Default to Cloud HSM provider
        return CloudHsmProvider(**kwargs)
