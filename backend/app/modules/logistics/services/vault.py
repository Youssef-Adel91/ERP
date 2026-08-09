"""
app/modules/logistics/services/vault.py — Carrier Webhook Secret Vault Resolution

Same simulated-Vault-resolution pattern used across this project
(app.modules.eta.services.gateway._resolve_client_secret,
app.modules.trust.services.hashing.get_vault_pepper,
app.plugins.whatsapp.services.vault.resolve_access_token): no live Vault
client exists here. CarrierAccount.webhook_secret_ref only ever stores a
`vault://...` reference, never a raw secret — this function is the single
stand-in for the real fetch.
"""
from __future__ import annotations


def resolve_webhook_secret(webhook_secret_ref: str | None) -> str:
    """
    Simulates fetching a carrier's real webhook HMAC secret from Vault
    given a `vault://...` reference. Raises ValueError if the tenant
    hasn't configured this carrier or the reference is malformed —
    callers must not silently fall back to an empty/no-op secret, since
    an empty secret disables signature verification entirely (see
    CarrierProvider.verify_webhook_signature's short-circuit).
    """
    if not webhook_secret_ref:
        raise ValueError("No webhook_secret_ref configured for this carrier account.")
    if not webhook_secret_ref.startswith("vault://"):
        raise ValueError("Invalid webhook_secret_ref format. Must be a vault:// URI.")

    # Simulated Vault retrieval (deterministic stand-in).
    return "resolved_vault_carrier_webhook_secret_value"
