"""JWT authentication — credential verification and token lifecycle."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from ..config import settings

_security = HTTPBearer()


def verify_credentials(username: str, password: str) -> bool:
    u_ok = secrets.compare_digest(username.encode(), settings.auth_username.encode())
    p_ok = secrets.compare_digest(password.encode(), settings.auth_password.encode())
    return u_ok and p_ok


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": username, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    exc = HTTPException(
        status_code=401,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        username: str | None = payload.get("sub")
        if not username:
            raise exc
        return username
    except JWTError:
        raise exc
