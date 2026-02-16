"""macOS Keychain integration for API key storage.

Uses the keyring library to store and retrieve API keys securely.
"""

from __future__ import annotations

import keyring

SERVICE_NAME = "ai-budget-dashboard"

# Map provider IDs to keychain account names
_ACCOUNT_MAP = {
    "anthropic": "anthropic-api-key",
    "openai": "openai-api-key",
    "google": "google-api-key",
    "xai": "xai-api-key",
}


def get_api_key(provider_id: str) -> str | None:
    """Retrieve an API key from the macOS Keychain.

    Returns None if no key is stored for this provider.
    """
    account = _ACCOUNT_MAP.get(provider_id, f"{provider_id}-api-key")
    try:
        return keyring.get_password(SERVICE_NAME, account)
    except Exception:
        return None


def set_api_key(provider_id: str, api_key: str) -> None:
    """Store an API key in the macOS Keychain."""
    account = _ACCOUNT_MAP.get(provider_id, f"{provider_id}-api-key")
    keyring.set_password(SERVICE_NAME, account, api_key)


def delete_api_key(provider_id: str) -> None:
    """Remove an API key from the macOS Keychain."""
    account = _ACCOUNT_MAP.get(provider_id, f"{provider_id}-api-key")
    try:
        keyring.delete_password(SERVICE_NAME, account)
    except keyring.errors.PasswordDeleteError:
        pass  # Key didn't exist
