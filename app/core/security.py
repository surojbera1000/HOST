"""Symmetric encryption for sensitive environment variables.

ইউজারের BOT_TOKEN / API_HASH ইত্যাদি database-এ কখনো plaintext-এ রাখা হয় না।
সব encrypt করে রাখা হয়, শুধু deploy করার সময় decrypt করা হয়।
"""
from cryptography.fernet import Fernet

from app.config import get_settings


def _cipher() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


def encrypt(value: str) -> str:
    """Plaintext string -> encrypted token (database-এ এটাই রাখা হয়)।"""
    return _cipher().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Encrypted token -> plaintext (শুধু deploy-এর সময়)।"""
    return _cipher().decrypt(token.encode()).decode()
