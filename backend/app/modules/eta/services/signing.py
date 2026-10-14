"""
app.modules.eta.services.signing — CAdES-BES Signing Providers Interface (Phase 5 - Step 3)

Defines:
  1. SigningProvider Protocol: interface for generating CAdES-BES signatures (FR-530, FR-533).
  2. CloudHsmProvider: ITIDA-approved Cloud HSM signing provider implementation.
  3. LocalHardwareTokenProvider: Local USB/eToken signing provider implementation.
  4. get_signing_provider: Factory to retrieve the appropriate signing provider for a tenant.

── REAL CRYPTOGRAPHIC SIGNING (replaces the earlier mock) ──────────────────────────
Both providers now produce a genuine CAdES-BES CMS SignedData structure (RFC 5652 /
ETSI EN 319 122) over the canonical document bytes, using `pyhanko`'s CAdES signer:
  - Real RSA/EC private key operation over the SHA-256 digest (no string concatenation).
  - Real embedded X.509 signing certificate + the CAdES `signing-certificate-v2` (ESS)
    signed attribute binding the signature to that certificate.
  - The resulting DER-encoded CMS ContentInfo is independently verifiable with any
    standard CMS/CAdES verifier (confirmed against `openssl cms -verify` during
    development — see docs/eta-signing-verification.md).

This closes the "fake signature" gap: the module can no longer report SIGNED for a
document that never underwent real cryptographic signing. What it still cannot do on
its own — because these require the tenant's real-world ETA registration, not code —
is:
  1. Hold a certificate issued by an ETA-approved CA (Egypt Trust / e-Finance / etc.).
     Until one is configured via `secret_ref` (see `_resolve_signing_material` below),
     signing raises `EtaSigningError` rather than silently fabricating a signature —
     this is a deliberate behavior change from the old mock, which always "succeeded".
  2. A local/sandbox self-signed certificate can be used ONLY when a caller explicitly
     opts in via `allow_self_signed_test_cert=True` (never the default), and every
     signature produced with it is stamped `signing_provider` with a `_TEST` suffix and
     `is_test_certificate: True` in the returned dict so it can never be mistaken for a
     real, ETA-acceptable signature downstream.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime as dt
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.modules.eta.exceptions import EtaException
from app.modules.eta.models.core import EtaSigningProvider


class EtaSigningError(EtaException):
    """Raised when cryptographic signing fails, no signing material is configured, or HSM is unreachable."""
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
          - "certificate_serial": Serial number of the real signing certificate
          - "issuer": Certificate Authority issuer string, read from the real certificate
          - "signing_provider": Provider identifier ("CLOUD_HSM" | "LOCAL_TOKEN" | etc.)
          - "signed_at": ISO8601 UTC timestamp of signature generation
          - "is_test_certificate": True only when signed with a local self-signed test cert
        """
        ...


# ── Real signing material resolution ─────────────────────────────────────────────

@dataclass
class SigningMaterial:
    """A loaded PKCS#12 bundle (private key + signing certificate + optional chain)."""
    pkcs12_bytes: bytes
    passphrase: bytes | None
    is_test_certificate: bool


def _resolve_signing_material(
    secret_ref: str | None,
    *,
    allow_self_signed_test_cert: bool = False,
) -> SigningMaterial:
    """
    Resolve the PKCS#12 (cert + private key) bundle to sign with.

    Real production path (not yet wired): `secret_ref` (e.g. "vault://eta/tenant/<id>/signing-cert")
    is resolved through the platform's Vault integration to a base64-encoded PKCS#12 bundle
    uploaded after the tenant completes real ETA CA registration. That Vault plumbing does not
    exist yet in this codebase (same stubbed state as `EtaGateway._resolve_client_secret`), so
    this function raises a clear, actionable error rather than fabricating a signature — this is
    an intentional behavior change from the previous mock, which always "succeeded" silently.

    Local file path (available today): `secret_ref` of the form "file:///abs/path/to/cert.p12"
    loads a real PKCS#12 bundle placed on disk — usable once a merchant has an actual
    ETA-issued certificate file, without needing Vault wired up first.

    Sandbox/dev fallback: when `secret_ref` is unset AND the caller explicitly passes
    `allow_self_signed_test_cert=True`, a locally generated, cached, clearly-labeled
    self-signed test certificate is used so the rest of the pipeline (canonicalization →
    hashing → CMS signing → submission state machine) can be exercised end-to-end before
    a real ETA-approved certificate exists. This path is NEVER used implicitly.
    """
    if secret_ref:
        if secret_ref.startswith("file://"):
            path = secret_ref[len("file://"):]
            if not os.path.isfile(path):
                raise EtaSigningError(
                    f"Configured signing certificate file not found at '{path}'. "
                    "Place the real .p12/.pfx bundle issued by your ETA-approved CA there."
                )
            with open(path, "rb") as fh:
                pkcs12_bytes = fh.read()
            passphrase_env = os.environ.get("ETA_SIGNING_CERT_PASSPHRASE")
            passphrase = passphrase_env.encode("utf-8") if passphrase_env else None
            return SigningMaterial(pkcs12_bytes=pkcs12_bytes, passphrase=passphrase, is_test_certificate=False)

        if secret_ref.startswith("vault://"):
            raise EtaSigningError(
                f"Cannot resolve signing certificate '{secret_ref}': Vault integration for ETA "
                "signing material is not yet implemented in this deployment. Configure a real "
                "PKCS#12 certificate bundle issued by an ETA-approved CA (Egypt Trust, e-Finance, "
                "or your Cloud HSM provider) and reference it via a 'file://' secret_ref, or wire "
                "up Vault secret resolution before enabling live ETA submission for this tenant."
            )

        raise EtaSigningError(f"Unrecognized signing secret_ref scheme: '{secret_ref}'.")

    if allow_self_signed_test_cert:
        return SigningMaterial(
            pkcs12_bytes=_get_or_create_test_certificate(),
            passphrase=None,
            is_test_certificate=True,
        )

    raise EtaSigningError(
        "No ETA signing certificate is configured for this tenant. A tenant must have a real "
        "digital certificate issued by an ETA-approved Certificate Authority (Egypt Trust, "
        "e-Finance, etc.) referenced via EtaTenantConfig.client_secret_ref / a dedicated signing "
        "secret_ref before documents can be signed and submitted. For sandbox pipeline testing "
        "only, pass allow_self_signed_test_cert=True explicitly."
    )


_TEST_CERT_CACHE_PATH = "/tmp/eta_sandbox_test_signing_cert.p12"
_test_cert_lock = threading.Lock()


def _get_or_create_test_certificate() -> bytes:
    """
    Generate (once) and cache a local self-signed RSA/X.509 certificate purely for exercising
    the CAdES-BES signing pipeline before a real ETA-issued certificate is available. This
    certificate will NEVER be accepted by the real Egyptian Tax Authority — it exists only to
    prove the cryptographic plumbing (canonicalization → hash → real CMS signature → structural
    verification) works, ahead of the tenant obtaining a real certificate.
    """
    with _test_cert_lock:
        if os.path.isfile(_TEST_CERT_CACHE_PATH):
            with open(_TEST_CERT_CACHE_PATH, "rb") as fh:
                return fh.read()

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "SANDBOX TEST CERTIFICATE - NOT ETA APPROVED"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Local Test Only"),
            x509.NameAttribute(NameOID.COUNTRY_NAME, "EG"),
        ])
        now = datetime.datetime.now(datetime.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=730))
            .sign(key, hashes.SHA256())
        )

        bundle = pkcs12.serialize_key_and_certificates(
            name=b"eta-sandbox-test",
            key=key,
            cert=cert,
            cas=None,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with open(_TEST_CERT_CACHE_PATH, "wb") as fh:
            fh.write(bundle)
        return bundle


async def _sign_cades_cms(
    canonical_bytes: bytes,
    material: SigningMaterial,
    provider_label: str,
) -> dict[str, Any]:
    """
    Perform the real CAdES-BES CMS SignedData signature (shared by both providers below —
    the cryptography is identical; only where the key material comes from differs).
    """
    if not canonical_bytes:
        raise EtaSigningError("Cannot sign empty canonical_bytes.")

    try:
        from pyhanko.sign.signers.pdf_cms import SimpleSigner
    except ImportError as exc:  # pragma: no cover
        raise EtaSigningError(
            "The 'pyhanko' package is required for real CAdES-BES signing but is not installed."
        ) from exc

    try:
        signer = SimpleSigner.load_pkcs12_data(
            pkcs12_bytes=material.pkcs12_bytes,
            other_certs=(),
            passphrase=material.passphrase,
        )
    except Exception as exc:
        raise EtaSigningError(f"Failed to load ETA signing certificate/key material: {exc}") from exc

    try:
        content_info = await signer.async_sign_general_data(
            canonical_bytes,
            "sha256",
            detached=True,
            use_cades=True,
        )
    except Exception as exc:
        raise EtaSigningError(f"CAdES-BES CMS signing operation failed: {exc}") from exc

    der_bytes = content_info.dump()
    signature_b64 = base64.b64encode(der_bytes).decode("ascii")

    cert = signer.signing_cert  # asn1crypto.x509.Certificate
    certificate_serial = format(cert.serial_number, "X")
    issuer = cert.issuer.human_friendly

    provider_id = f"{provider_label}_TEST" if material.is_test_certificate else provider_label

    return {
        "signatureType": "I",
        "value": signature_b64,
        "signature_b64": signature_b64,
        "certificate_serial": certificate_serial,
        "issuer": issuer,
        "signing_provider": provider_id,
        "signed_at": dt.now(UTC).isoformat(),
        "is_test_certificate": material.is_test_certificate,
    }


class CloudHsmProvider:
    """
    ITIDA-approved Cloud HSM Signing Provider (e.g., Egypt Trust / MCDR Cloud HSM).

    Performs real CAdES-BES CMS signing (see module docstring). `secret_ref` should point at
    the tenant's real signing certificate bundle once available; `allow_self_signed_test_cert`
    lets the sandbox pipeline be exercised before that exists.
    """

    def __init__(
        self,
        hsm_url: str = "https://hsm.egypttrust.com/api/v1/sign",
        key_id: str | None = None,
        secret_ref: str | None = None,
        allow_self_signed_test_cert: bool = False,
    ) -> None:
        self.hsm_url = hsm_url
        self.key_id = key_id or "default-hsm-key"
        self.secret_ref = secret_ref
        self.allow_self_signed_test_cert = allow_self_signed_test_cert

    async def sign_cades_bes(self, canonical_bytes: bytes, tenant_id: UUID) -> dict[str, Any]:
        material = _resolve_signing_material(
            self.secret_ref, allow_self_signed_test_cert=self.allow_self_signed_test_cert
        )
        return await _sign_cades_cms(canonical_bytes, material, "CLOUD_HSM")


class LocalHardwareTokenProvider:
    """
    Local USB Hardware Token / eToken signing provider.

    NOTE: a real USB/eToken (PKCS#11) integration requires calling out to a local signing
    agent process that has the physical token attached — that agent does not exist in this
    codebase and cannot be built or tested from a cloud environment with no USB token present.
    This provider currently signs with the same real CMS/CAdES cryptographic path as
    CloudHsmProvider (via a loaded PKCS#12 bundle) so the rest of the pipeline is exercised
    correctly; wiring an actual PKCS#11 hardware token is separate follow-up work that needs
    the physical token present to build against.
    """

    def __init__(
        self,
        agent_url: str = "http://localhost:8899/api/sign",
        secret_ref: str | None = None,
        allow_self_signed_test_cert: bool = False,
    ) -> None:
        self.agent_url = agent_url
        self.secret_ref = secret_ref
        self.allow_self_signed_test_cert = allow_self_signed_test_cert

    async def sign_cades_bes(self, canonical_bytes: bytes, tenant_id: UUID) -> dict[str, Any]:
        material = _resolve_signing_material(
            self.secret_ref, allow_self_signed_test_cert=self.allow_self_signed_test_cert
        )
        return await _sign_cades_cms(canonical_bytes, material, "LOCAL_TOKEN")


def get_signing_provider(provider_type: EtaSigningProvider, **kwargs: Any) -> SigningProvider:
    """
    Factory to instantiate the configured signing provider for an ETA tenant.
    """
    if provider_type == EtaSigningProvider.CLOUD_HSM:
        return CloudHsmProvider(
            hsm_url=kwargs.get("hsm_url", "https://hsm.egypttrust.com/api/v1/sign"),
            key_id=kwargs.get("key_id"),
            secret_ref=kwargs.get("secret_ref"),
            allow_self_signed_test_cert=kwargs.get("allow_self_signed_test_cert", False),
        )
    elif provider_type == EtaSigningProvider.LOCAL_AGENT:
        return LocalHardwareTokenProvider(
            agent_url=kwargs.get("agent_url", "http://localhost:8899/api/sign"),
            secret_ref=kwargs.get("secret_ref"),
            allow_self_signed_test_cert=kwargs.get("allow_self_signed_test_cert", False),
        )
    else:
        # Default to Cloud HSM provider
        return CloudHsmProvider(**kwargs)
