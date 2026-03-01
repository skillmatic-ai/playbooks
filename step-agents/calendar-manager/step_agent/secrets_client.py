"""Secrets Client — Read org secrets (OAuth tokens + AI keys) from Firestore.

Step agents run on GKE with Workload Identity. The Electron desktop app
writes OAuth tokens and AI API keys to orgs/{orgId}/secrets/{secretId}
via the client SDK. This module reads them via firebase-admin (Admin SDK),
which bypasses Firestore security rules.

Usage:
    from step_agent.secrets_client import read_ai_config, read_oauth_token

    ai = read_ai_config(org_id)       # {'provider': 'anthropic', 'apiKey': '...', 'model': '...'}
    gmail = read_oauth_token(org_id, 'gmail')  # {'accessToken': '...', ...}
"""

from step_agent.firestore_client import _get_db


def read_ai_config(org_id: str) -> dict:
    """Read AI API key config from Firestore org secrets.

    Returns dict with keys: provider, apiKey, model.
    Raises ValueError if the secret does not exist.
    """
    ref = _get_db().collection("orgs").document(org_id).collection("secrets").document("ai_api_key")
    snap = ref.get()
    if not snap.exists:
        raise ValueError(
            f"AI API key not configured for org {org_id}. "
            "Please configure an AI provider in the Skillmatic desktop app."
        )
    data = snap.to_dict()
    return {
        "provider": data.get("provider", "anthropic"),
        "apiKey": data["apiKey"],
        "model": data.get("model", "claude-sonnet-4-20250514"),
    }


def read_oauth_token(org_id: str, service: str) -> dict:
    """Read an OAuth token from Firestore org secrets.

    Args:
        org_id: The organization ID.
        service: One of 'gmail', 'slack', 'jira'.

    Returns dict with keys: accessToken, refreshToken, expiresAt, scopes.
    Raises ValueError if the secret does not exist.
    """
    ref = _get_db().collection("orgs").document(org_id).collection("secrets").document(service)
    snap = ref.get()
    if not snap.exists:
        raise ValueError(
            f"{service.capitalize()} OAuth token not found for org {org_id}. "
            f"Please connect {service.capitalize()} in the Skillmatic desktop app."
        )
    data = snap.to_dict()
    return {
        "accessToken": data["accessToken"],
        "refreshToken": data.get("refreshToken"),
        "expiresAt": data.get("expiresAt", 0),
        "scopes": data.get("scopes", []),
    }
