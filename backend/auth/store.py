"""Client accounts (self sign-up). The internal admin account still comes from settings."""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone

import aiosqlite

from ..db import DB_PATH

_ITERATIONS = 200_000

_SQL_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    company_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'client',
    created_at    TEXT NOT NULL
)
"""


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(_SQL_USERS)
        await db.commit()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS).hex()
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


def _row(r) -> dict:
    return {"id": r[0], "email": r[1], "password_hash": r[2], "company_name": r[3], "role": r[4], "created_at": r[5]}


async def create_user(email: str, password: str, company_name: str) -> dict | None:
    """Create a client account. Returns None if the email is already registered."""
    row = (uuid.uuid4().hex, email.strip(), hash_password(password), company_name.strip(), "client",
           datetime.now(timezone.utc).isoformat())
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO users (id, email, password_hash, company_name, role, created_at) VALUES (?,?,?,?,?,?)", row)
        except aiosqlite.IntegrityError:
            return None
        await db.commit()
    return _row(row)


async def get_by_email(email: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, email, password_hash, company_name, role, created_at FROM users WHERE email = ?",
                               (email.strip(),))
        r = await cur.fetchone()
    return _row(r) if r else None


async def get_by_id(user_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, email, password_hash, company_name, role, created_at FROM users WHERE id = ?",
                               (user_id,))
        r = await cur.fetchone()
    return _row(r) if r else None


async def list_clients() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, email, password_hash, company_name, role, created_at FROM users "
                               "WHERE role = 'client' ORDER BY created_at DESC")
        rows = await cur.fetchall()
    return [_row(r) for r in rows]
