"""Secrets handling: random tokens, one-way hashes, and reversible encryption.

- Session / invitation / OAuth-state tokens are random and stored only as a
  SHA-256 hash (they're bearer secrets; the plaintext lives in the cookie/link).
- Xero OAuth tokens must be recoverable to call the API, so they're encrypted
  with MultiFernet: encrypt with the newest key, decrypt with any listed key.
  Rotating = prepend a new key, re-encrypt lazily on next refresh, then drop
  the old key once nothing uses it.
"""

import base64
import hashlib
import json
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet

from .config import get_settings


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


@lru_cache
def _cipher() -> MultiFernet:
    keys = [k.strip() for k in get_settings().token_encryption_keys.split(",") if k.strip()]
    if not keys:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEYS is not set. Generate one with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return MultiFernet([Fernet(k) for k in keys])


def encrypt_json(data: dict) -> str:
    return _cipher().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(blob: str) -> dict:
    return json.loads(_cipher().decrypt(blob.encode()))
