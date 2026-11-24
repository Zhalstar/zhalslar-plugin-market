"""Public marketplace and owner plugin management routes."""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer, selectinload
from sqlalchemy.orm.attributes import flag_modified

from ..config import get_settings
from ..dependencies import CurrentUser, Database
from ..market import normalized_version, plugin_response
from ..models import OAuthAccount, Plugin, PluginVersion, new_id
from ..packages import store_package
from ..providers import RepositoryProvider, RepositorySnapshot
from ..schemas import (
    ClaimPluginsRequest,
    MessageResponse,
    PluginDetailResponse,
    PluginPage,
    PluginResponse,
    PluginVersionResponse,
    PublishPluginRequest,
    RepositoryResponse,
)
from ..security import decrypt_oauth_token

router = APIRouter(prefix="/plugins", tags=["Plugins"])


async def _claimable_repositories(
    db: Database, user_id: str, plugins: list[Plugin]
) -> dict[str, RepositoryResponse]:
    """Match unowned entries against fresh platform-authorized repositories.

    Args:
        db: Open database session.
        user_id: Authenticated marketplace account.
        plugins: Unowned records to match.

    Returns:
        Authorized repository keyed by marketplace plugin ID.
    """
    matches = {}
    providers = {"github": "github.com", "gitee": "gitee.com"}
    for account in db.scalars(
        select(OAuthAccount).where(OAuthAccount.user_id == user_id)
    ):
        host = providers.get(account.provider)
        if not host:
            continue
        candidates = [
            plugin
            for plugin in plugins
            if plugin.repo_url.casefold().startswith(f"https://{host}/")
            and plugin.provider in {None, account.provider}
        ]
        if not candidates:
            continue
        client = RepositoryProvider(
            account.provider, decrypt_oauth_token(account.access_token_encrypted)
        )
        repositories = await client.list_repositories()
        by_id = {repo.id: repo for repo in repositories}
        by_url = {repo.url.casefold(): repo for repo in repositories}
        for plugin in candidates:
            repo = (
                by_id.get(plugin.provider_repo_id)
                if plugin.provider_repo_id
                else by_url.get(
                    plugin.repo_url.rstrip("/").casefold().removesuffix(".git")
                )
            )
            if repo is not None:
                matches[plugin.id] = repo
    return matches


@router.get("/claimable", response_model=list[PluginResponse])
async def claimable_plugins(user: CurrentUser, db: Database) -> list[PluginResponse]:
    """List unowned plugins that match a linked repository.

    Args:
        user: Authenticated marketplace account.
        db: Open database session.

    Returns:
        Claimable plugin records.
    """
    plugins = list(
        db.scalars(
            select(Plugin).where(Plugin.owner_id.is_(None)).order_by(Plugin.market_id)
        )
    )
    matches = await _claimable_repositories(db, user.id, plugins)
    return [plugin_response(plugin) for plugin in plugins if plugin.id in matches]


@router.post("/claim", response_model=list[PluginResponse])
async def claim_plugins(
    payload: ClaimPluginsRequest, user: CurrentUser, db: Database
) -> list[PluginResponse]:
    """Bind selected unowned entries without publishing new versions.

    Args:
        payload: IDs of existing market entries.
        user: Authenticated marketplace account.
        db: Open database session.

    Returns:
        Newly claimed plugin records.

    Raises:
        HTTPException: If any entry is already owned or no longer eligible.
    """
    ids = set(payload.plugin_ids)
    plugins = list(
        db.scalars(select(Plugin).where(Plugin.id.in_(ids)).order_by(Plugin.id))
    )
    if len(plugins) != len(ids) or any(
        plugin.owner_id is not None for plugin in plugins
    ):
        raise HTTPException(
            status_code=409, detail="Some plugins are no longer claimable"
        )
    matches = await _claimable_repositories(db, user.id, plugins)
    if len(matches) != len(ids):
        raise HTTPException(
            status_code=403, detail="Repository is not claimable by this account"
        )
    originals = {
        plugin.id: (plugin.provider, plugin.provider_repo_id, plugin.repo_url)
        for plugin in plugins
    }
    plugins = list(
        db.scalars(
            select(Plugin)
            .where(Plugin.id.in_(ids))
            .order_by(Plugin.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(plugins) != len(ids) or any(
        plugin.owner_id is not None
        or originals[plugin.id]
        != (plugin.provider, plugin.provider_repo_id, plugin.repo_url)
        for plugin in plugins
    ):
        raise HTTPException(
            status_code=409, detail="Some plugins are no longer claimable"
        )
    for plugin in plugins:
        repository = matches[plugin.id]
        plugin.owner_id = user.id
        plugin.provider = repository.provider
        plugin.provider_repo_id = repository.id
        plugin.repo_full_name = repository.full_name
        plugin.default_branch = repository.default_branch
        # Ownership is not a new release and must not move the entry in the market.
        flag_modified(plugin, "updated_at")
    db.commit()
    return [plugin_response(plugin) for plugin in plugins]


def _linked_provider(db: Database, user_id: str, provider: str) -> RepositoryProvider:
    """Create a provider client from a user's linked account.

    Args:
        db: Open database session.
        user_id: Marketplace user ID.
        provider: Repository provider identifier.

    Returns:
        Authenticated provider client.

    Raises:
        HTTPException: If the account is not linked.
    """
    account = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user_id,
            OAuthAccount.provider == provider,
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Provider account is not linked")
    return RepositoryProvider(
        provider, decrypt_oauth_token(account.access_token_encrypted)
    )


def _json_safe_metadata(snapshot: RepositorySnapshot) -> dict:
    """Normalize YAML values for JSON database storage.

    Args:
        snapshot: Validated repository snapshot.

    Returns:
        JSON-safe metadata object.
    """
    return json.loads(
        json.dumps(snapshot.metadata_raw, ensure_ascii=False, default=str)
    )


async def archive_snapshot(
    db: Session, plugin: Plugin, snapshot: RepositorySnapshot
) -> None:
    """Apply a validated repository snapshot to a plugin entity.

    Args:
        db: Active transaction.
        plugin: Plugin entity with its ID assigned.
        snapshot: Validated repository snapshot.
    """
    checksum, size = await store_package(snapshot.repository, snapshot.commit_sha)
    metadata = snapshot.metadata
    release = db.scalar(
        select(PluginVersion)
        .where(
            PluginVersion.plugin_id == plugin.id,
            PluginVersion.version == metadata.version,
            PluginVersion.package_sha256.is_(None),
        )
        .order_by(PluginVersion.published_at.desc())
        .limit(1)
    )
    if release is None:
        release = PluginVersion(
            id=new_id(), plugin_id=plugin.id, version=metadata.version
        )
        db.add(release)
    release.commit_sha = snapshot.commit_sha
    release.package_sha256 = checksum
    release.package_bytes = size
    release.metadata_json = _json_safe_metadata(snapshot)
    plugin.market_id = f"{metadata.author}/{metadata.name}"
    plugin.provider_repo_id = snapshot.repository.id
    plugin.repo_full_name = snapshot.repository.full_name
    plugin.repo_url = snapshot.repository.url.rstrip("/")
    plugin.default_branch = snapshot.repository.default_branch
    plugin.commit_sha = snapshot.commit_sha
    plugin.author = metadata.author
    plugin.name = metadata.name
    plugin.display_name = metadata.display_name
    plugin.version = metadata.version
    plugin.description = metadata.desc
    plugin.short_description = metadata.short_desc
    if snapshot.logo_bytes is not None:
        settings = get_settings()
        asset_name = hashlib.sha256(snapshot.logo_bytes).hexdigest() + ".png"
        (settings.storage.directory / asset_name).write_bytes(snapshot.logo_bytes)
        plugin.logo_url = f"{settings.storage.public_path.rstrip('/')}/{asset_name}"
    else:
        plugin.logo_url = snapshot.logo_url
    plugin.readme = snapshot.readme
    plugin.download_url = f"/api/v1/plugins/{plugin.id}/versions/{release.id}/download"
    plugin.metadata_json = release.metadata_json
    plugin.stars = (
        snapshot.repository.stars
        if snapshot.repository.stars is not None
        else plugin.stars
    )
    plugin.documents = {
        "ref": snapshot.commit_sha,
        "items": {key: doc.model_dump() for key, doc in snapshot.documents.items()},
    }
    plugin.sync_state = "failed" if snapshot.docs_failed else "ready"


@router.get("", response_model=PluginPage)
def list_plugins(
    db: Database,
    search: str = Query(default="", max_length=100),
    provider: str = Query(default="", max_length=20),
    page: int = Query(default=1, ge=1, le=1_000_000),
    page_size: int = Query(default=9, ge=0, le=48),
    sort: Literal["updated", "newest", "stars", "name"] = "updated",
) -> PluginPage:
    """Browse published plugins with optional search and provider filters.

    Args:
        db: Open database session.
        search: Name, author, or description search text.
        provider: Optional repository provider filter.
        page: One-based page number.
        page_size: Maximum plugins per page, or zero for all matches.
        sort: Order to apply before pagination.

    Returns:
        Matching published plugins for the requested page and their total count.
    """
    query = select(Plugin).where(Plugin.status == "published")
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Plugin.display_name.ilike(pattern),
                Plugin.name.ilike(pattern),
                Plugin.author.ilike(pattern),
                Plugin.description.ilike(pattern),
            )
        )
    if provider.strip():
        query = query.where(Plugin.provider == provider.strip())
    total = db.scalar(query.with_only_columns(func.count(Plugin.id))) or 0
    order = {
        "updated": (Plugin.updated_at.desc(),),
        "newest": (Plugin.created_at.desc(),),
        "stars": (Plugin.stars.desc().nulls_last(), Plugin.updated_at.desc()),
        "name": (
            func.lower(
                func.coalesce(func.nullif(Plugin.display_name, ""), Plugin.name)
            ),
        ),
    }
    query = query.options(
        defer(Plugin.documents), defer(Plugin.readme), selectinload(Plugin.owner)
    ).order_by(*order[sort], Plugin.id)
    if page_size:
        query = query.offset((page - 1) * page_size).limit(page_size)
    return PluginPage(
        items=[plugin_response(plugin) for plugin in db.scalars(query)], total=total
    )


@router.get("/mine", response_model=list[PluginResponse])
def my_plugins(user: CurrentUser, db: Database) -> list[PluginResponse]:
    """List plugins owned by the current user, including unpublished entries.

    Args:
        user: Authenticated user.
        db: Open database session.

    Returns:
        User-owned plugins.
    """
    plugins = db.scalars(
        select(Plugin)
        .where(Plugin.owner_id == user.id)
        .order_by(Plugin.updated_at.desc())
    ).all()
    return [plugin_response(plugin) for plugin in plugins]


@router.get("/{plugin_id}/logo", include_in_schema=False)
async def plugin_logo(plugin_id: str, db: Database) -> Response:
    """Fetch and persist a trusted legacy plugin logo on first access.

    Args:
        plugin_id: Plugin database ID.
        db: Open database session.

    Returns:
        PNG image response with public caching enabled.

    Raises:
        HTTPException: If the plugin, asset host, or PNG data is invalid.
    """
    plugin = db.get(Plugin, plugin_id)
    if plugin is None or plugin.status != "published" or not plugin.logo_url:
        raise HTTPException(status_code=404, detail="Plugin logo not found")

    settings = get_settings()
    parsed = urlparse(plugin.logo_url)
    if parsed.scheme != "https" or parsed.hostname not in set(
        settings.security.allowed_asset_hosts
    ):
        raise HTTPException(status_code=422, detail="Plugin logo host is not allowed")

    try:
        content = bytearray()
        async with (
            httpx.AsyncClient(
                timeout=settings.market.request_timeout_seconds
            ) as client,
            client.stream("GET", plugin.logo_url, follow_redirects=False) as response,
        ):
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > settings.market.max_logo_bytes:
                    raise HTTPException(
                        status_code=422, detail="Plugin logo is too large"
                    )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Plugin logo fetch failed") from exc
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=422, detail="Plugin logo is not a PNG image")

    asset_name = hashlib.sha256(plugin.market_id.encode()).hexdigest()[:32] + ".png"
    (settings.storage.directory / asset_name).write_bytes(content)
    plugin.logo_url = f"{settings.storage.public_path.rstrip('/')}/{asset_name}"
    db.commit()
    return Response(
        content=bytes(content),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{plugin_id}/versions/{release_id}/download")
def download_package(plugin_id: str, release_id: str, db: Database) -> FileResponse:
    """Serve a stored ZIP only while its plugin is publicly listed."""
    plugin = db.get(Plugin, plugin_id)
    release = db.get(PluginVersion, release_id)
    if (
        plugin is None
        or plugin.status != "published"
        or release is None
        or release.plugin_id != plugin_id
        or not release.package_sha256
    ):
        raise HTTPException(status_code=404, detail="Plugin archive not found")
    path = get_settings().storage.packages_directory / f"{release.package_sha256}.zip"
    if not path.is_file() or path.stat().st_size != release.package_bytes:
        raise HTTPException(status_code=404, detail="Plugin archive not found")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{plugin.name}-{release.version}.zip",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/{plugin_id}", response_model=PluginDetailResponse)
def get_plugin(plugin_id: str, db: Database) -> PluginDetailResponse:
    """Return one published plugin by database or market ID.

    Args:
        plugin_id: Database UUID or URL-encoded market ID.
        db: Open database session.

    Returns:
        Matching plugin.

    Raises:
        HTTPException: If the plugin is not published.
    """
    plugin = db.scalar(
        select(Plugin).where(
            or_(Plugin.id == plugin_id, Plugin.market_id == plugin_id),
            Plugin.status == "published",
        )
    )
    if plugin is None:
        raise HTTPException(status_code=404, detail="Plugin not found")
    documents = plugin.documents or {}
    versions = [
        PluginVersionResponse(
            version=release.version,
            commit_sha=release.commit_sha,
            published_at=release.published_at,
            download_url=(
                f"/api/v1/plugins/{plugin.id}/versions/{release.id}/download"
                if release.package_sha256
                else None
            ),
            package_bytes=release.package_bytes,
            package_sha256=release.package_sha256,
        )
        for release in sorted(
            plugin.versions, key=lambda release: release.published_at, reverse=True
        )
    ]
    return PluginDetailResponse(
        **plugin_response(plugin).model_dump(),
        publisher_name=plugin.owner.display_name
        if plugin.owner and plugin.owner.is_active
        else None,
        sync_state=plugin.sync_state or "pending",
        docs_ref=documents.get("ref", ""),
        documents=documents.get("items", {}),
        versions=versions,
    )


@router.post("/publish", response_model=PluginResponse, status_code=201)
async def publish_plugin(
    payload: PublishPluginRequest, user: CurrentUser, db: Database
) -> PluginResponse:
    """Publish a plugin from a linked repository without claiming existing entries.

    Args:
        payload: Provider and repository selection.
        user: Authenticated user.
        db: Open database session.

    Returns:
        Published plugin.

    Raises:
        HTTPException: If ownership, metadata, or identity validation fails.
    """
    client = _linked_provider(db, user.id, payload.provider)
    repository = await client.repository_by_id(payload.repository_id)
    canonical = repository.url.casefold()
    existing = list(
        db.scalars(
            select(Plugin).where(
                or_(
                    (Plugin.provider == repository.provider)
                    & (Plugin.provider_repo_id == repository.id),
                    func.lower(func.rtrim(Plugin.repo_url, "/")).in_(
                        [canonical, f"{canonical}.git"]
                    ),
                )
            )
        )
    )
    if any(plugin.owner_id is None for plugin in existing):
        raise HTTPException(
            status_code=409, detail="Claim this plugin before publishing"
        )
    if any(plugin.owner_id != user.id for plugin in existing):
        raise HTTPException(
            status_code=409, detail="Repository already has a market entry"
        )
    snapshot = await client.snapshot(repository)
    try:
        remote_version = normalized_version(snapshot.metadata.version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    market_id = f"{snapshot.metadata.author}/{snapshot.metadata.name}"
    plugin = db.scalar(
        select(Plugin).where(Plugin.market_id == market_id).with_for_update()
    )
    if existing and any(item.market_id != market_id for item in existing):
        raise HTTPException(
            status_code=409, detail="Repository already has a market entry"
        )
    if plugin is not None and (
        (plugin.provider, plugin.provider_repo_id)
        != (repository.provider, repository.id)
        if plugin.provider_repo_id
        else plugin.repo_url.rstrip("/").casefold().removesuffix(".git") != canonical
    ):
        raise HTTPException(
            status_code=409, detail="Plugin ID belongs to another repository"
        )
    if plugin is not None and plugin.owner_id is None:
        raise HTTPException(
            status_code=409, detail="Claim this plugin before publishing"
        )
    if plugin is not None and plugin.owner_id != user.id:
        raise HTTPException(status_code=409, detail="Plugin ID is already published")
    if plugin is None:
        plugin = Plugin(
            id=new_id(),
            market_id=market_id,
            owner_id=user.id,
            provider=payload.provider,
            repo_url=snapshot.repository.url,
            author=snapshot.metadata.author,
            name=snapshot.metadata.name,
            version=snapshot.metadata.version,
            description=snapshot.metadata.desc,
        )
        db.add(plugin)
        archive_required = True
    else:
        current = normalized_version(plugin.version)
        if remote_version < current:
            raise HTTPException(
                status_code=409, detail="Cannot publish an older version"
            )
        archive_required = remote_version > current or not any(
            release.package_sha256 and release.version == plugin.version
            for release in plugin.versions
        )
        if (
            archive_required
            and remote_version == current
            and plugin.commit_sha
            and plugin.commit_sha != snapshot.commit_sha
        ):
            raise HTTPException(
                status_code=409,
                detail="Bump the version before publishing a different commit",
            )
    plugin.owner_id = user.id
    plugin.provider = payload.provider
    plugin.status = "published"
    try:
        if archive_required:
            with db.no_autoflush:
                await archive_snapshot(db, plugin, snapshot)
        else:
            plugin.stars = (
                snapshot.repository.stars
                if snapshot.repository.stars is not None
                else plugin.stars
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Plugin ID is already published"
        ) from exc
    db.refresh(plugin)
    return plugin_response(plugin)


@router.post("/{plugin_id}/check-update", response_model=PluginResponse)
async def check_update(
    plugin_id: str, user: CurrentUser, db: Database
) -> PluginResponse:
    """Fetch metadata and publish a strictly newer repository version.

    Args:
        plugin_id: Plugin database ID.
        user: Authenticated owner.
        db: Open database session.

    Returns:
        Updated plugin.

    Raises:
        HTTPException: If ownership is invalid or no newer version exists.
    """
    plugin = db.get(Plugin, plugin_id, with_for_update=True)
    if plugin is None or plugin.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Plugin not found")
    if not plugin.provider or not plugin.provider_repo_id:
        raise HTTPException(status_code=409, detail="Plugin has no linked repository")
    client = _linked_provider(db, user.id, plugin.provider)
    snapshot = await client.snapshot(
        await client.repository_by_id(plugin.provider_repo_id)
    )
    expected_market_id = f"{snapshot.metadata.author}/{snapshot.metadata.name}"
    if expected_market_id != plugin.market_id:
        raise HTTPException(
            status_code=422, detail="Plugin author or name cannot change during update"
        )
    current_version = normalized_version(plugin.version)
    try:
        remote_version = normalized_version(snapshot.metadata.version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if remote_version <= current_version:
        if (
            snapshot.repository.stars is not None
            and snapshot.repository.stars != plugin.stars
        ):
            plugin.stars = snapshot.repository.stars
            db.commit()
        raise HTTPException(
            status_code=409,
            detail=f"No newer version found; current version is {plugin.version}",
        )
    await archive_snapshot(db, plugin, snapshot)
    db.commit()
    db.refresh(plugin)
    return plugin_response(plugin)


@router.post("/{plugin_id}/unpublish", response_model=MessageResponse)
def unpublish(plugin_id: str, user: CurrentUser, db: Database) -> MessageResponse:
    """Remove an owned plugin from public marketplace results.

    Args:
        plugin_id: Plugin database ID.
        user: Authenticated owner.
        db: Open database session.

    Returns:
        Unpublish confirmation.

    Raises:
        HTTPException: If the plugin is not owned by the current user.
    """
    plugin = db.get(Plugin, plugin_id)
    if plugin is None or plugin.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Plugin not found")
    plugin.status = "unpublished"
    db.commit()
    return MessageResponse(message="Plugin unpublished")
