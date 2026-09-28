"""Authentication primitives; neither raw session tokens nor model keys enter logs."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

_hasher = PasswordHasher()
_dummy_hash = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(encoded: str | None, password: str) -> bool:
    try:
        matched = _hasher.verify(encoded or _dummy_hash, password)
        return encoded is not None and matched
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CredentialCipher:
    def __init__(self, keys: list[str]):
        if not keys:
            raise ValueError("Model encryption key is not configured")
        try:
            self._cipher = MultiFernet([Fernet(key.encode()) for key in keys])
        except (ValueError, TypeError):
            raise ValueError("Model encryption key is invalid") from None

    def encrypt(self, value: str) -> str:
        return self._cipher.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._cipher.decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            raise ValueError("Model credential cannot be decrypted") from None

    def rotate(self, value: str) -> str:
        try:
            return self._cipher.rotate(value.encode()).decode()
        except (InvalidToken, ValueError):
            raise ValueError("Model credential cannot be rotated") from None
