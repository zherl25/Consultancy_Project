"""JWT authentication — credential verification, token lifecycle and role checks.

Two roles: the internal "admin" (credentials from settings; chat and projects)
and "client" companies that sign up themselves to generate documentation.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from ..config import settings
from . import store

_security = HTTPBearer()

ADMIN = "admin"
CLIENT = "client"


@dataclass
class CurrentUser:
    id: str          # username for the admin, user id for clients
    role: str


def verify_credentials(username: str, password: str) -> bool:
    u_ok = secrets.compare_digest(username.encode(), settings.auth_username.encode())
    p_ok = secrets.compare_digest(password.encode(), settings.auth_password.encode())
    return u_ok and p_ok


async def authenticate(username: str, password: str) -> CurrentUser | None:
    if verify_credentials(username, password):
        return CurrentUser(id=username, role=ADMIN)
    user = await store.get_by_email(username)
    if user and store.check_password(password, user["password_hash"]):
        return CurrentUser(id=user["id"], role=user["role"])
    return None


def create_access_token(subject: str, role: str = ADMIN) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": subject, "role": role, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> CurrentUser:
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
    except JWTError:
        raise exc
    subject: str | None = payload.get("sub")
    if not subject:
        raise exc
    # Tokens issued before roles existed only ever belonged to the admin
    return CurrentUser(id=subject, role=payload.get("role", ADMIN))


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="This area is for consultants only.")
    return user


async def require_client(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != CLIENT:
        raise HTTPException(status_code=403, detail="This area is for client accounts.")
    return user
