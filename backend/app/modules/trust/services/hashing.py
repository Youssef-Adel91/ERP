"""
app.modules.trust.services.hashing — Trust Network Cryptography (Phase 7a)

Handles HMAC-SHA256 hashing for phone numbers using a PEPPER fetched from the Vault.
"""
from __future__ import annotations

import hmac
import re
from hashlib import sha256


def get_vault_pepper(pepper_ref: str = "vault://secrets/trust/pepper/v1") -> str:
    """
    Simulates fetching the pepper from a secure Vault via reference.
    In a real implementation, this would call a Vault client (e.g., HashiCorp Vault).
    """
    if pepper_ref.startswith("vault://"):
        # Simulated Vault retrieval
        return "b7f9d8e4a2c1..."  # Deterministic test pepper
    
    raise ValueError("Invalid pepper reference format. Must be a vault:// URI.")


def hash_phone_number(phone: str, pepper: str | None = None) -> str:
    """
    Normalizes a phone number to E.164-like format (digits only + country code assumption)
    and computes an HMAC-SHA256 hash using the provided pepper.
    
    Raises ValueError if phone is invalid.
    """
    # 1. Normalize: strip non-digits (e.g., "+20 10-1234-5678" -> "201012345678")
    normalized = re.sub(r"\D", "", phone)
    
    # Simple E.164 enforcement for Egyptian numbers (must start with 20 and have 12 digits)
    if not normalized.startswith("20") or len(normalized) != 12:
        # Fallback: if it's a 10-digit local number (e.g. 01012345678 -> 11 digits), prefix with 2
        if len(normalized) == 11 and normalized.startswith("0"):
            normalized = "2" + normalized
        else:
            raise ValueError(f"Invalid phone number format for hashing: {phone}")

    # 2. Hash
    secret_key = (pepper or get_vault_pepper()).encode("utf-8")
    msg = normalized.encode("utf-8")
    
    return hmac.new(secret_key, msg, digestmod=sha256).hexdigest()
