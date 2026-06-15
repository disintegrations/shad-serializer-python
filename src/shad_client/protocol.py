"""Cryptographic helpers for Shad's encrypted HTTP protocol."""

from __future__ import annotations

import base64
import json
from typing import Any, Mapping

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ZERO_IV = b"\0" * 16


def transform_v6(value: str) -> str:
    """Apply the reversible substitution used by API v6."""
    result = []
    for char in value:
        if "0" <= char <= "9":
            result.append(chr((13 - (ord(char) - ord("0"))) % 10 + ord("0")))
        elif "A" <= char <= "Z":
            result.append(chr((29 - (ord(char) - ord("A"))) % 26 + ord("A")))
        elif "a" <= char <= "z":
            result.append(chr((32 - (ord(char) - ord("a"))) % 26 + ord("a")))
        else:
            result.append(char)
    return "".join(result)


def derive_aes_key(auth: str) -> bytes:
    """Derive the 32-byte AES key from an auth token or temporary session."""
    if len(auth) < 32:
        raise ValueError("Shad auth/tmp_session must contain at least 32 characters")

    shuffled = auth[16:24] + auth[0:8] + auth[24:32] + auth[8:16]
    result = []
    for char in shuffled:
        if "0" <= char <= "9":
            result.append(chr((ord(char) - ord("0") + 5) % 10 + ord("0")))
        elif "a" <= char <= "z":
            result.append(chr((ord(char) - ord("a") + 9) % 26 + ord("a")))
        else:
            raise ValueError("Shad auth/tmp_session must use lowercase ASCII letters or digits")
    return "".join(result).encode("ascii")


def encrypt_data(value: Mapping[str, Any], auth: str) -> str:
    """Encrypt a JSON-compatible mapping for a Shad request."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    encryptor = Cipher(algorithms.AES(derive_aes_key(auth)), modes.CBC(ZERO_IV)).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


def decrypt_data(value: str, auth: str) -> dict[str, Any]:
    """Decrypt a Shad response into a dictionary."""
    decryptor = Cipher(algorithms.AES(derive_aes_key(auth)), modes.CBC(ZERO_IV)).decryptor()
    padded = decryptor.update(base64.b64decode(value)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    raw = unpadder.update(padded) + unpadder.finalize()
    return json.loads(raw.decode("utf-8"))

