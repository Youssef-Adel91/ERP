"""
app.modules.eta.services.crypto — ETA CAdES-BES SHA-256 Hashing Engine (FR-532)

Provides cryptographic hashing over the UTF-8 bytes of canonicalized ETA documents
as required for CAdES-BES electronic signing (Type I and Type S signatures).
"""
from __future__ import annotations

import hashlib


def compute_cades_bes_hash(canonical_string: str | bytes) -> str:
    """
    Compute the SHA-256 hexadecimal digest over the UTF-8 bytes of an ETA canonical string (FR-532).

    Args:
        canonical_string: The ETA canonical string (or UTF-8 encoded bytes).

    Returns:
        64-character lowercase hexadecimal SHA-256 digest.
    """
    payload_bytes = _ensure_bytes(canonical_string)
    return hashlib.sha256(payload_bytes).hexdigest()


def compute_cades_bes_hash_bytes(canonical_string: str | bytes) -> bytes:
    """
    Compute the raw SHA-256 binary digest over the UTF-8 bytes of an ETA canonical string.

    Args:
        canonical_string: The ETA canonical string (or UTF-8 encoded bytes).

    Returns:
        32-byte raw SHA-256 digest (useful for PKCS#11 hardware token / HSM signatures).
    """
    payload_bytes = _ensure_bytes(canonical_string)
    return hashlib.sha256(payload_bytes).digest()


def _ensure_bytes(data: str | bytes) -> bytes:
    if isinstance(data, str):
        return data.encode("utf-8")
    return data
