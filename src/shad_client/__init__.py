"""Unofficial synchronous Python client for Shad Messenger."""

from .client import ShadClient, ShadError
from .protocol import decrypt_data, derive_aes_key, encrypt_data, transform_v6

__all__ = [
    "ShadClient",
    "ShadError",
    "decrypt_data",
    "derive_aes_key",
    "encrypt_data",
    "transform_v6",
]

__version__ = "0.1.0"

