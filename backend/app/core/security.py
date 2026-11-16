import hashlib
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import get_settings
from app.core.errors import AppError

_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"not-the-password", bcrypt.gensalt())
_jwks_client: PyJWKClient | None = None
logger = logging.getLogger("vansoraai")


class WindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str) -> None:
        if get_settings().app_env == "test":
            return
        now = time.monotonic()
        recent = [stamp for stamp in self._hits.get(key, []) if now - stamp < self.window_seconds]
        if len(recent) >= self.limit:
            raise AppError("rate_limited", "Too many attempts. Try again shortly.", 429)
        recent.append(now)
        self._hits[key] = recent


auth_rate_limiter = WindowLimiter(limit=10, window_seconds=60)
upload_rate_limiter = WindowLimiter(limit=15, window_seconds=600)
generation_rate_limiter = WindowLimiter(limit=40, window_seconds=600)
support_rate_limiter = WindowLimiter(limit=30, window_seconds=600)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def verify_password_or_dummy(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        bcrypt.checkpw(password.encode(), _DUMMY_PASSWORD_HASH)
        return False
    return verify_password(password, password_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(*, user_id: uuid.UUID, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        if settings.auth_mode == "supabase":
            return _decode_supabase_token(token)
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppError("invalid_token", "Sign in again to continue.", 401) from exc


def _decode_supabase_token(token: str) -> dict:
    settings = get_settings()
    if not settings.supabase_url and not settings.supabase_jwt_secret:
        raise AppError("auth_not_configured", "Supabase Auth is not configured on the server.", 500)

    try:
        if settings.supabase_jwt_secret:
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            claims = _decode_with_jwks(token)
    except jwt.PyJWTError as exc:
        logger.warning("Local Supabase JWT check failed: %s", exc)
        claims = _claims_from_supabase_user(token)

    if not claims.get("sub"):
        raise AppError("invalid_token", "Sign in again to continue.", 401)
    if not claims.get("email"):
        user = _supabase_user(token)
        claims = {**claims, "email": user.get("email"), "user_metadata": user.get("user_metadata") or {}}
    return claims


def _claims_from_supabase_user(token: str) -> dict:
    user = _supabase_user(token)
    return {"sub": user.get("id"), "email": user.get("email"), "user_metadata": user.get("user_metadata") or {}}


def _supabase_user(token: str) -> dict:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": settings.supabase_service_role_key,
        },
        timeout=20,
    )
    if response.status_code != 200:
        raise AppError("invalid_token", "Sign in again to continue.", 401)
    user = response.json()
    if not isinstance(user, dict) or not user.get("id") or not user.get("email"):
        raise AppError("invalid_token", "Sign in again to continue.", 401)
    return user


def _decode_with_jwks(token: str) -> dict:
    global _jwks_client
    settings = get_settings()
    if _jwks_client is None:
        _jwks_client = PyJWKClient(f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience="authenticated",
    )
