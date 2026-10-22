"""Accounts: password hashing, session cookies and the current-user dependencies.

Design
------
* Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library) and a random 16-byte salt.
* Signing in creates a random session token. The browser gets it in an HttpOnly cookie, so
  page scripts cannot read it; the database stores only its SHA-256 hash.
* Sessions expire after SESSION_DAYS and are deleted on sign-out.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import database as db
from config import get_settings

COOKIE_NAME = "waypoint_session"
_ALGORITHM = "pbkdf2_sha256"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or get_settings().password_iterations
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != _ALGORITHM:
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def burn_time(password: str) -> None:
    """Hash anyway when the email is unknown, so response time does not reveal which emails exist."""
    hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), b"0" * 16, get_settings().password_iterations)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; they are always stored in UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def start_session(session: AsyncSession, user: db.User, response: Response) -> None:
    """Create a session row and set the cookie on the response."""
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.session_days)
    session.add(db.AuthSession(token_hash=_hash_token(token), user_id=user.id, expires_at=expires))
    await session.execute(delete(db.AuthSession).where(db.AuthSession.expires_at < datetime.now(timezone.utc)))
    await session.commit()
    response.set_cookie(
        COOKIE_NAME, token, max_age=settings.session_days * 86400, httponly=True,
        secure=settings.cookie_secure, samesite=settings.cookie_samesite, path="/")


async def end_session(session: AsyncSession, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await session.execute(delete(db.AuthSession).where(db.AuthSession.token_hash == _hash_token(token)))
        await session.commit()
    clear_cookie(response)


def clear_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True,
                           secure=settings.cookie_secure, samesite=settings.cookie_samesite)


async def get_optional_user(request: Request, session: AsyncSession = Depends(db.get_session)) -> db.User | None:
    """The signed-in user, or None for anonymous visitors."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    row = (await session.execute(
        select(db.AuthSession).where(db.AuthSession.token_hash == _hash_token(token)))).scalar_one_or_none()
    if row is None or as_utc(row.expires_at) < datetime.now(timezone.utc):
        return None
    return await session.get(db.User, row.user_id)


async def get_current_user(user: db.User | None = Depends(get_optional_user)) -> db.User:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user
