"""AES-256-GCM symmetric encryption for storing OAuth tokens at rest."""
import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _derive_key() -> bytes:
    return hashlib.sha256(settings.secret_key.encode()).digest()


def encrypt(plaintext: str) -> str:
    """Return base64url-encoded nonce + ciphertext."""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key()).encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt(blob: str) -> str:
    """Decrypt a blob produced by encrypt()."""
    raw = base64.urlsafe_b64decode(blob.encode())
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_derive_key()).decrypt(nonce, ciphertext, None).decode()
