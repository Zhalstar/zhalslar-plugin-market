"""Marketplace serialization, import, and version comparison."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import Plugin, PluginVersion
from .schemas import PluginResponse


def normalized_version(value: str) -> Version:
    """Parse a plugin version with optional leading `v`.

    Args:
        value: Metadata version string.

    Returns:
        Parsed PEP 440 version.

    Raises:
        ValueError: If the version is empty or invalid.
    """
    try:
        return Version(value.strip().removeprefix("v"))
    except InvalidVersion as exc:
        raise ValueError(f"Invalid plugin version: {value}") from exc


def metadata_labels(value: Any) -> list[str]:
    """Normalize authored tag and platform labels for display."""
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(
            item.strip()[:80]
            for item in value
            if isinstance(item, str) and item.strip()
        )
    )[:32]


def plugin_response(plugin: Plugin) -> PluginResponse:
    """Serialize a plugin for the web frontend.

    Args:
        plugin: Stored plugin entity.

    Returns:
        Frontend plugin response.
    """
    return PluginResponse(
        id=plugin.id,
        market_id=plugin.market_id,
        author=plugin.author,
        name=plugin.name,
        display_name=plugin.display_name,
        version=plugin.version,
        repo=plugin.repo_url,
        desc=plugin.description,
        short_desc=plugin.short_description,
        logo=(
            plugin.logo_url
            if not plugin.logo_url or plugin.logo_url.startswith("/")
            else f"/api/v1/plugins/{plugin.id}/logo"
        ),
        download_url=plugin.download_url,
        provider=plugin.provider,
        owner_id=plugin.owner_id,
        publisher_avatar_url=(
            plugin.owner.avatar_url if plugin.owner and plugin.owner.is_active else None
        ),
        stars=plugin.stars,
        astrbot_version=str(plugin.metadata_json.get("astrbot_version") or ""),
        support_platforms=metadata_labels(
            plugin.metadata_json.get("support_platforms")
        ),
        tags=metadata_labels(plugin.metadata_json.get("tags")),
        status=plugin.status,
        created_at=plugin.created_at,
        updated_at=plugin.updated_at,
    )


def market_record(plugin: Plugin) -> dict[str, Any]:
    """Build one AstrBot-compatible market record.

    Args:
        plugin: Published plugin.

    Returns:
        Compatible market record.
    """
    record = dict(plugin.metadata_json)
    record.update(
        {
            "author": plugin.author,
            "name": plugin.name,
            "version": plugin.version,
            "repo": plugin.repo_url,
            "desc": plugin.description,
        }
    )
    settings = get_settings()
    logo_url = plugin.logo_url
    if logo_url.startswith("/"):
        logo_url = f"{settings.app.public_url.rstrip('/')}{logo_url}"
    elif logo_url:
        logo_url = (
            f"{settings.app.public_url.rstrip('/')}/api/v1/plugins/{plugin.id}/logo"
        )
    optional = {
        "display_name": plugin.display_name,
        "short_desc": plugin.short_description,
        "logo": logo_url,
        "download_url": (
            f"{settings.app.public_url.rstrip('/')}{plugin.download_url}"
            if plugin.download_url.startswith("/")
            else plugin.download_url
        ),
    }
    for key, value in optional.items():
        if value:
            record[key] = value
        else:
            record.pop(key, None)
    if plugin.stars is not None:
        record["stars"] = plugin.stars
    else:
        record.pop("stars", None)
    return record


def build_market_document(
    db: Session, settings: Settings | None = None
) -> dict[str, Any]:
    """Build the complete AstrBot marketplace document.

    Args:
        db: Open database session.
        settings: Optional configuration override.

    Returns:
        Marketplace metadata and published plugin records.
    """
    settings = settings or get_settings()
    plugins = db.scalars(
        select(Plugin)
        .where(Plugin.status == "published")
        .order_by(func.lower(Plugin.market_id))
    ).all()
    latest_update = max(
        (plugin.updated_at for plugin in plugins),
        default=datetime(1970, 1, 1, tzinfo=timezone.utc),
    )
    document: dict[str, Any] = {
        "$meta": {
            "schema_version": 1,
            "name": settings.market.title,
            "version": latest_update.isoformat(),
            "homepage": settings.app.public_url,
            "description": settings.market.description,
            "updated_at": latest_update.isoformat(),
        }
    }
    for plugin in plugins:
        document[plugin.market_id] = market_record(plugin)
    return document


def market_bytes(db: Session) -> bytes:
    """Serialize the market document deterministically.

    Args:
        db: Open database session.

    Returns:
        UTF-8 JSON bytes.
    """
    return (
        json.dumps(build_market_document(db), ensure_ascii=False, indent=2) + "\n"
    ).encode()


def seed_market(db: Session, seed_path: Path | None = None) -> int:
    """Import a legacy market JSON only when the plugin table is empty.

    Args:
        db: Open database session.
        seed_path: Optional seed file override.

    Returns:
        Number of imported plugins.

    Raises:
        ValueError: If the seed document contains invalid records.
    """
    if db.scalar(select(func.count()).select_from(Plugin)):
        return 0
    path = seed_path or get_settings().market.seed_file
    if not path.is_file():
        return 0
    document = json.loads(path.read_text(encoding="utf-8"))
    imported = 0
    for market_id, record in document.items():
        if market_id == "$meta":
            continue
        if not isinstance(record, dict):
            raise ValueError(f"Invalid seed record: {market_id}")
        for field in ("author", "name", "version", "repo", "desc"):
            if not str(record.get(field) or "").strip():
                raise ValueError(f"{market_id}: missing {field}")
        normalized_version(str(record["version"]))
        repo_url = str(record["repo"]).rstrip("/")
        repo_full_name = repo_url.removeprefix("https://github.com/")
        plugin = Plugin(
            market_id=market_id,
            repo_full_name=repo_full_name,
            repo_url=repo_url,
            author=str(record["author"]),
            name=str(record["name"]),
            display_name=str(record.get("display_name") or ""),
            version=str(record["version"]),
            description=str(record["desc"]),
            short_description=str(record.get("short_desc") or ""),
            logo_url=str(record.get("logo") or ""),
            download_url=str(record.get("download_url") or ""),
            metadata_json=record,
        )
        db.add(plugin)
        db.flush()
        db.add(
            PluginVersion(
                plugin_id=plugin.id,
                version=plugin.version,
                metadata_json=record,
            )
        )
        imported += 1
    db.commit()
    return imported


def market_md5(db: Session) -> str:
    """Calculate the current compatible marketplace fingerprint.

    Args:
        db: Open database session.

    Returns:
        Lowercase MD5 digest expected by AstrBot.
    """
    return hashlib.md5(market_bytes(db), usedforsecurity=False).hexdigest()
