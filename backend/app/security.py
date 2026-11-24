"""Password hashing, signed sessions, and OAuth token encryption."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import RefreshToken, User

password_hasher = PasswordHasher()
ACCESS_COOKIE = "market_access"
REFRESH_COOKIE = "market_refresh"


def hash_password(password: str) -> str:
    """Hash a user password with Argon2id.

    Args:
        password: Plaintext password.

    Returns:
        Encoded Argon2 password hash.
    """
    return password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a password without leaking mismatch details.

    Args:
        password: Submitted plaintext password.
        encoded_hash: Stored Argon2 hash.

    Returns:
        Whether the password matches.
    """
    try:
        return password_hasher.verify(encoded_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(user: User, settings: Settings | None = None) -> str:
    """Create a short-lived signed access token.

    Args:
        user: Authenticated user.
        settings: Optional configuration override.

    Returns:
        Encoded JWT access token.
    """
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth.access_token_minutes),
    }
    return jwt.encode(payload, settings.auth.secret_key, algorithm="HS256")


def create_oauth_state(
    user: User, provider: str, settings: Settings | None = None
) -> str:
    """Create a short-lived signed OAuth callback state.

    Args:
        user: User linking the provider.
        provider: Provider identifier.
        settings: Optional configuration override.

    Returns:
        Encoded OAuth state JWT.
    """
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user.id,
            "provider": provider,
            "type": "oauth_state",
            "nonce": secrets.token_urlsafe(16),
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        settings.auth.secret_key,
        algorithm="HS256",
    )


def decode_token(
    token: str, expected_type: str, settings: Settings | None = None
) -> dict[str, Any]:
    """Decode a signed JWT and verify its token type.

    Args:
        token: Encoded JWT.
        expected_type: Required token type claim.
        settings: Optional configuration override.

    Returns:
        Decoded token claims.

    Raises:
        HTTPException: If the token is invalid, expired, or the wrong type.
    """
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.auth.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from exc
    if payload.get("type") != expected_type or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return payload


def token_hash(token: str) -> str:
    """Create a database-safe SHA-256 token digest.

    Args:
        token: Opaque refresh token.

    Returns:
        Hex-encoded digest.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session(
    response: Response,
    db: Session,
    user: User,
    settings: Settings | None = None,
) -> None:
    """Issue access and refresh cookies and persist the refresh token.

    Args:
        response: API response receiving cookies.
        db: Open database session.
        user: Authenticated user.
        settings: Optional configuration override.
    """
    settings = settings or get_settings()
    refresh = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.auth.refresh_token_days
    )
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash(refresh),
            expires_at=expires_at,
        )
    )
    db.commit()
    response.set_cookie(
        ACCESS_COOKIE,
        create_access_token(user, settings),
        max_age=settings.auth.access_token_minutes * 60,
        httponly=True,
        secure=settings.auth.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=settings.auth.refresh_token_days * 86400,
        httponly=True,
        secure=settings.auth.secure_cookies,
        samesite="lax",
        path="/api/v1/auth",
    )


def clear_session(response: Response) -> None:
    """Remove browser authentication cookies.

    Args:
        response: API response receiving cookie removals.
    """
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


def current_user_from_request(request: Request, db: Session) -> User:
    """Resolve an active user from the access cookie.

    Args:
        request: Current HTTP request.
        db: Open database session.

    Returns:
        Authenticated active user.

    Raises:
        HTTPException: If authentication is missing or invalid.
    """
    token = request.cookies.get(ACCESS_COOKIE, "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    payload = decode_token(token, "access")
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def _fernet(settings: Settings | None = None) -> Fernet:
    """Create the OAuth credential cipher.

    Args:
        settings: Optional configuration override.

    Returns:
        Configured Fernet cipher.

    Raises:
        RuntimeError: If OAuth encryption is not configured.
    """
    settings = settings or get_settings()
    key = settings.oauth.encryption_key.strip()
    if not key:
        raise RuntimeError("OAUTH_ENCRYPTION_KEY is required for OAuth")
    try:
        return Fernet(key.encode())
    except ValueError:
        derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        return Fernet(derived)


def encrypt_oauth_token(token: str) -> str:
    """Encrypt a provider access token for storage.

    Args:
        token: Provider access token.

    Returns:
        Fernet-encrypted token string.
    """
    return _fernet().encrypt(token.encode()).decode()


def decrypt_oauth_token(encrypted_token: str) -> str:
    """Decrypt a stored provider access token.

    Args:
        encrypted_token: Stored encrypted value.

    Returns:
        Plain provider token.

    Raises:
        HTTPException: If the stored credential cannot be decrypted.
    """
    try:
        return _fernet().decrypt(encrypted_token.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(
            status_code=500, detail="Linked account credentials are unavailable"
        ) from exc


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    """Revoke a refresh token when it exists.

    Args:
        db: Open database session.
        raw_token: Browser refresh token.
    """
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw_token))
    )
    if stored is not None:
        stored.revoked = True
        db.commit()
