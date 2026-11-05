"""Symmetric encryption for sensitive environment variables.

Values like BOT_TOKEN / API_HASH are never stored as plaintext in the database.
Everything is encrypted at rest and only decrypted at deploy time.
"""
from cryptography.fernet import Fernet

from app.config import get_settings


def _cipher() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


def encrypt(value: str) -> str:
    """Plaintext string -> encrypted token (this is what gets stored)."""
    return _cipher().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Encrypted token -> plaintext (only at deploy time)."""
    return _cipher().decrypt(token.encode()).decode()
