"""Email and password authentication routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from ..config import get_settings
from ..dependencies import CurrentUser, Database
from ..models import RefreshToken, User
from ..schemas import LoginRequest, MessageResponse, RegisterRequest, UserResponse
from ..security import (
    REFRESH_COOKIE,
    clear_session,
    hash_password,
    issue_session,
    revoke_refresh_token,
    token_hash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: RegisterRequest, response: Response, db: Database) -> User:
    """Create a new email account and start its browser session.

    Args:
        payload: Registration fields.
        response: HTTP response receiving authentication cookies.
        db: Open database session.

    Returns:
        Newly created user.

    Raises:
        HTTPException: If the email address is already registered.
    """
    email = payload.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        email_verified=not get_settings().auth.require_email_verification,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    issue_session(response, db, user)
    return user


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response, db: Database) -> User:
    """Authenticate an email account and issue browser cookies.

    Args:
        payload: Login credentials.
        response: HTTP response receiving authentication cookies.
        db: Open database session.

    Returns:
        Authenticated user.

    Raises:
        HTTPException: If credentials are invalid or the account is disabled.
    """
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    issue_session(response, db, user)
    return user


@router.post("/refresh", response_model=UserResponse)
def refresh(request: Request, response: Response, db: Database) -> User:
    """Rotate a valid refresh token and issue a new session.

    Args:
        request: Current request containing the refresh cookie.
        response: HTTP response receiving rotated cookies.
        db: Open database session.

    Returns:
        Authenticated user.

    Raises:
        HTTPException: If the refresh token is unavailable or expired.
    """
    raw_token = request.cookies.get(REFRESH_COOKIE, "")
    stored = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash(raw_token),
            RefreshToken.revoked.is_(False),
        )
    )
    expires_at = stored.expires_at if stored else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if stored is None or expires_at is None or expires_at <= datetime.now(timezone.utc):
        clear_session(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    stored.revoked = True
    db.commit()
    issue_session(response, db, user)
    return user


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: Database) -> MessageResponse:
    """Revoke the current refresh token and clear browser cookies.

    Args:
        request: Current request.
        response: HTTP response receiving cookie removals.
        db: Open database session.

    Returns:
        Logout confirmation.
    """
    raw_token = request.cookies.get(REFRESH_COOKIE, "")
    if raw_token:
        revoke_refresh_token(db, raw_token)
    clear_session(response)
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> User:
    """Return the currently authenticated user.

    Args:
        user: Authenticated user dependency.

    Returns:
        Current user.
    """
    return user
