"""Fernet encryption for Gmail OAuth tokens using HKDF key derivation."""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


def _get_fernet() -> Fernet:
    """Derive Fernet key from Django SECRET_KEY using HKDF."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"synco-gmail-credentials",
        info=b"fernet-key",
    )
    key = hkdf.derive(settings.SECRET_KEY.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_data(data: bytes) -> bytes:
    """Encrypt data using Fernet with HKDF-derived key."""
    return _get_fernet().encrypt(data)


def decrypt_data(data: bytes) -> bytes:
    """Decrypt data using Fernet with HKDF-derived key."""
    return _get_fernet().decrypt(data)
