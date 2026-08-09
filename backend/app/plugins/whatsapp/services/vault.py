"""
app/plugins/whatsapp/services/vault.py — WhatsApp Access Token Vault Resolution

Same simulated-Vault-resolution pattern as
app.modules.eta.services.gateway.EtaGateway._resolve_client_secret and
app.modules.trust.services.hashing.get_vault_pepper: no live Vault client
exists anywhere in this project. Real credential values are never stored
in Postgres — only a `vault://...` reference string
(WhatsAppTenantConfig.access_token_ref) — and this function is the single
place that stands in for the real Vault fetch. Swapping in a genuine
HashiCorp Vault (or AWS Secrets Manager, etc.) client later only touches
this one function.
"""
from __future__ import annotations


def resolve_access_token(access_token_ref: str | None) -> str:
    """
    Simulates fetching the real WhatsApp Cloud API bearer token from Vault
    given a `vault://...` reference. Raises ValueError if the tenant hasn't
    configured a token yet or the reference is malformed — callers must
    not silently fall back to a global/shared token.
    """
    if not access_token_ref:
        raise ValueError("No WhatsApp access_token_ref configured for this tenant.")
    if not access_token_ref.startswith("vault://"):
        raise ValueError("Invalid access_token_ref format. Must be a vault:// URI.")

    # Simulated Vault retrieval (deterministic stand-in, mirrors
    # trust.services.hashing.get_vault_pepper / eta.services.gateway's
    # _resolve_client_secret).
    return "resolved_vault_whatsapp_token_value"
