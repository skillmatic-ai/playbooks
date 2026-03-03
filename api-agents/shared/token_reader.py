"""
token_reader.py — Read and decrypt OAuth tokens from Firestore for API agents.

API agents running in GKE containers use this module to fetch the encrypted
OAuth token for the assigned user + service, then decrypt it via Cloud KMS.

The token is stored at:
  orgs/{orgId}/members/{uid}/tokens/{service}

Encrypted using AES-256-GCM envelope encryption (see token-encryption.ts):
  wrappedDEK.iv.ciphertext.authTag (all base64)

Usage:
    from token_reader import get_access_token

    token = await get_access_token(org_id, uid, service)
    # Use token to call the external API
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.cloud import firestore, kms

KMS_PROJECT = os.environ.get("GCP_PROJECT_ID", "skillmatic-ea1ab")
KMS_LOCATION = "us-central1"
KMS_KEY_RING = "skillmatic-keys"
KMS_KEY = "oauth-token-key"

KMS_KEY_NAME = (
    f"projects/{KMS_PROJECT}/locations/{KMS_LOCATION}"
    f"/keyRings/{KMS_KEY_RING}/cryptoKeys/{KMS_KEY}"
)

# Module-level singletons (initialized lazily)
_db: firestore.AsyncClient | None = None
_kms: kms.KeyManagementServiceClient | None = None


def _get_db() -> firestore.AsyncClient:
    global _db
    if _db is None:
        _db = firestore.AsyncClient(project=KMS_PROJECT)
    return _db


def _get_kms() -> kms.KeyManagementServiceClient:
    global _kms
    if _kms is None:
        _kms = kms.KeyManagementServiceClient()
    return _kms


def _decrypt_envelope(envelope: str) -> str:
    """Decrypt an envelope-encrypted token string.

    Envelope format: wrappedDEK.iv.ciphertext.authTag (base64-encoded parts)
    """
    parts = envelope.split(".")
    if len(parts) != 4:
        raise ValueError("Invalid encrypted envelope format")

    wrapped_dek_b64, iv_b64, ciphertext_b64, auth_tag_b64 = parts
    wrapped_dek = base64.b64decode(wrapped_dek_b64)
    iv = base64.b64decode(iv_b64)
    ciphertext = base64.b64decode(ciphertext_b64)
    auth_tag = base64.b64decode(auth_tag_b64)

    # Unwrap DEK via Cloud KMS
    client = _get_kms()
    response = client.decrypt(
        request={"name": KMS_KEY_NAME, "ciphertext": wrapped_dek}
    )
    dek = response.plaintext

    # Decrypt with AES-256-GCM (ciphertext + authTag concatenated for AESGCM)
    aesgcm = AESGCM(dek)
    plaintext = aesgcm.decrypt(iv, ciphertext + auth_tag, None)

    return plaintext.decode("utf-8")


async def get_token_doc(
    org_id: str, uid: str, service: str
) -> dict | None:
    """Fetch the raw token document from Firestore (encrypted fields)."""
    db = _get_db()
    doc_ref = db.document(f"orgs/{org_id}/members/{uid}/tokens/{service}")
    doc = await doc_ref.get()
    if not doc.exists:
        return None
    return doc.to_dict()


async def get_access_token(org_id: str, uid: str, service: str) -> str:
    """Fetch and decrypt the access token for a user + service.

    Raises:
        ValueError: If no token document exists.
    """
    doc = await get_token_doc(org_id, uid, service)
    if doc is None:
        raise ValueError(
            f"No OAuth token found for user {uid}, service {service} in org {org_id}"
        )

    encrypted_access = doc.get("accessToken")
    if not encrypted_access:
        raise ValueError(f"Token document exists but accessToken is empty")

    return _decrypt_envelope(encrypted_access)


async def get_refresh_token(org_id: str, uid: str, service: str) -> str | None:
    """Fetch and decrypt the refresh token (if present).

    Returns None if no refresh token was stored.
    """
    doc = await get_token_doc(org_id, uid, service)
    if doc is None:
        raise ValueError(
            f"No OAuth token found for user {uid}, service {service} in org {org_id}"
        )

    encrypted_refresh = doc.get("refreshToken")
    if not encrypted_refresh:
        return None

    return _decrypt_envelope(encrypted_refresh)


async def has_token(org_id: str, uid: str, service: str) -> bool:
    """Check if a token exists for the user + service (no decryption)."""
    doc = await get_token_doc(org_id, uid, service)
    return doc is not None
