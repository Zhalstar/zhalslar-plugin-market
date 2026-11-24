"""GitHub and Gitee account linking routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..config import get_settings
from ..dependencies import CurrentUser, Database
from ..models import OAuthAccount
from ..providers import (
    RepositoryProvider,
    exchange_oauth_code,
    oauth_authorize_url,
    provider_config,
)
from ..schemas import MessageResponse, OAuthAccountResponse, RepositoryResponse
from ..security import (
    create_oauth_state,
    decode_token,
    decrypt_oauth_token,
    encrypt_oauth_token,
)

router = APIRouter(prefix="/oauth", tags=["Repository accounts"])


@router.get("/accounts", response_model=list[OAuthAccountResponse])
def list_accounts(user: CurrentUser, db: Database) -> list[OAuthAccount]:
    """List repository accounts linked to the current user.

    Args:
        user: Authenticated user.
        db: Open database session.

    Returns:
        Linked accounts without access tokens.
    """
    return list(
        db.scalars(
            select(OAuthAccount)
            .where(OAuthAccount.user_id == user.id)
            .order_by(OAuthAccount.provider)
        ).all()
    )


@router.get("/{provider}/connect")
def connect(provider: str, user: CurrentUser) -> dict[str, str]:
    """Start an OAuth account-linking flow.

    Args:
        provider: Repository provider identifier.
        user: Authenticated user.

    Returns:
        External authorization URL.
    """
    provider_config(provider)
    state = create_oauth_state(user, provider)
    return {"url": oauth_authorize_url(provider, state)}


@router.get("/{provider}/callback")
async def callback(
    provider: str, code: str, state: str, db: Database, user: CurrentUser
) -> RedirectResponse:
    """Exchange an OAuth code and save the linked account.

    Args:
        provider: Repository provider identifier.
        code: Provider authorization code.
        state: Signed linking state.
        db: Open database session.
        user: Marketplace account in the browser completing authorization.

    Returns:
        Redirect to the frontend account settings page.

    Raises:
        HTTPException: If the state user or provider is invalid.
    """
    payload = decode_token(state, "oauth_state")
    if payload.get("provider") != provider:
        raise HTTPException(status_code=400, detail="OAuth provider mismatch")
    if payload.get("sub") != user.id:
        raise HTTPException(status_code=403, detail="OAuth session mismatch")
    token = await exchange_oauth_code(provider, code)
    identity = await RepositoryProvider(provider, token).current_identity()
    provider_user_id = str(identity.get("id") or "")
    username = str(identity.get("login") or identity.get("name") or "")
    if not provider_user_id or not username:
        raise HTTPException(status_code=502, detail="Invalid provider identity")

    account = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == provider,
        )
    )
    if account is None:
        account = OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            username=username,
            access_token_encrypted=encrypt_oauth_token(token),
        )
        db.add(account)
    else:
        account.provider_user_id = provider_user_id
        account.username = username
        account.access_token_encrypted = encrypt_oauth_token(token)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This provider account is linked to another user"
        ) from exc
    frontend_url = get_settings().app.frontend_url.rstrip("/")
    target = f"{frontend_url}/settings/accounts?linked={provider}"
    return RedirectResponse(target, status_code=303)


@router.delete("/{provider}", response_model=MessageResponse)
def unlink(provider: str, user: CurrentUser, db: Database) -> MessageResponse:
    """Unlink one repository provider account.

    Args:
        provider: Repository provider identifier.
        user: Authenticated user.
        db: Open database session.

    Returns:
        Unlink confirmation.

    Raises:
        HTTPException: If no matching link exists.
    """
    account = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == provider,
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Linked account not found")
    db.delete(account)
    db.commit()
    return MessageResponse(message=f"{provider.title()} account unlinked")


@router.get("/{provider}/repositories", response_model=list[RepositoryResponse])
async def repositories(
    provider: str, user: CurrentUser, db: Database
) -> list[RepositoryResponse]:
    """List repositories available through a linked account.

    Args:
        provider: Repository provider identifier.
        user: Authenticated user.
        db: Open database session.

    Returns:
        Public repositories eligible for publishing and claiming.

    Raises:
        HTTPException: If the provider account is not linked.
    """
    account = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == provider,
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Provider account is not linked")
    token = decrypt_oauth_token(account.access_token_encrypted)
    return await RepositoryProvider(provider, token).list_repositories()
