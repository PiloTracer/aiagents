from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from passlib.context import CryptContext

from .config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str | int, expires_delta: Optional[int] = None) -> str:
    expire_seconds = expires_delta or settings.AUTH_TOKEN_TTL_SECONDS
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=expire_seconds)
    to_encode: dict[str, Any] = {"sub": str(subject), "exp": expire, "iat": now}
    encoded_jwt = jwt.encode(to_encode, settings.AUTH_TOKEN_SECRET, algorithm="HS256")
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.AUTH_TOKEN_SECRET, algorithms=["HS256"])

