import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

password_hash = PasswordHash(
    (
        Argon2Hasher(),
        BcryptHasher(),
    )
)
ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    expire = datetime.now(UTC) + expires_delta
    jti = str(uuid.uuid4())
    to_encode = {"exp": expire, "sub": str(subject), "jti": jti}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def generate_refresh_token() -> str:
    """Generate a cryptographically secure refresh token."""
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)
