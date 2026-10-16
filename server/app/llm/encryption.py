"""
AES-256-GCM encryption for user API keys.
Keys are encrypted at rest — plaintext only exists in memory during request lifecycle.
"""

from __future__ import annotations

import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import get_settings


def _get_aes_key() -> bytes:
    """Derive the 32-byte AES key from the server encryption key env var."""
    raw = get_settings().server_encryption_key
    # If it's hex-encoded (64 chars), decode it. Otherwise hash it to 32 bytes.
    if len(raw) == 64:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    # Fallback: SHA-256 hash of the raw string to get exactly 32 bytes
    import hashlib
    return hashlib.sha256(raw.encode()).digest()


def encrypt_api_key(plaintext_key: str) -> tuple[bytes, bytes]:
    """
    Encrypt an API key string.
    Returns (encrypted_key, nonce) — both stored in DB as BYTEA.
    """
    aes_key = _get_aes_key()
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    aesgcm = AESGCM(aes_key)
    encrypted = aesgcm.encrypt(nonce, plaintext_key.encode("utf-8"), None)
    return encrypted, nonce


def decrypt_api_key(encrypted_key: bytes, nonce: bytes) -> str:
    """
    Decrypt an API key. Returns the plaintext string.
    Only called during LLM proxy requests — never stored or logged.
    """
    aes_key = _get_aes_key()
    aesgcm = AESGCM(aes_key)
    plaintext = aesgcm.decrypt(nonce, encrypted_key, None)
    return plaintext.decode("utf-8")
