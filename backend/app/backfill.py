"""Fetch documents and matching archives for previously imported plugins."""

import argparse
import asyncio
import os
import re
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select

from .api.plugins import archive_snapshot
from .database import SessionLocal
from .market import normalized_version
from .models import Plugin
from .packages import store_package
from .providers import RepositoryProvider
from .schemas import RepositoryResponse


async def run(offset: int, limit: int, *, archives_only: bool = False) -> int:
    """Backfill a stable slice of public entries, committing each independently.

    Args:
        offset: Number of published entries to skip.
        limit: Maximum number of entries to process.
        archives_only: Restore missing ZIPs from recorded commits without syncing docs.

    Returns:
        Number of entries that could not be processed.
    """
    failures = 0
    orgs: dict[str, dict[str, RepositoryResponse]] = {}
    with SessionLocal() as db:
        ids = db.scalars(
            select(Plugin.id)
            .where(Plugin.status == "published")
            .order_by(Plugin.market_id)
            .offset(offset)
            .limit(limit)
        ).all()
        for plugin_id in ids:
            plugin = db.get(Plugin, plugin_id, with_for_update=True)
            if plugin is None or plugin.status != "published":
                db.rollback()
                continue
            market_id = plugin.market_id
            try:
                url = urlsplit(plugin.repo_url)
                provider = {"github.com": "github", "gitee.com": "gitee"}.get(
                    url.hostname
                )
                full_name = url.path.strip("/").removesuffix(".git")
                if (
                    url.scheme != "https"
                    or not provider
                    or not re.fullmatch(r"[\w.-]+/[\w.-]+", full_name)
                ):
                    raise ValueError("Unsupported repository URL")
                org, repo_name = full_name.split("/", 1)
                if archives_only:
                    release = next(
                        (
                            item
                            for item in plugin.versions
                            if item.version == plugin.version
                        ),
                        None,
                    )
                    if release is None or release.package_sha256:
                        db.rollback()
                        continue
                    ref = (
                        release.commit_sha
                        or plugin.commit_sha
                        or (plugin.documents or {}).get("ref", "")
                    )
                    if not re.fullmatch(r"[a-f0-9]{40}", ref):
                        raise ValueError("No recorded commit for this version")
                    repository = RepositoryResponse(
                        provider=provider,
                        id=plugin.provider_repo_id or "",
                        full_name=full_name,
                        owner=org,
                        name=repo_name,
                        url=plugin.repo_url,
                        default_branch=plugin.default_branch,
                        private=False,
                        can_push=False,
                    )
                    release.package_sha256, release.package_bytes = await store_package(
                        repository, ref, expected_release=(market_id, release.version)
                    )
                    release.commit_sha = ref
                    plugin.commit_sha = ref
                    plugin.download_url = (
                        f"/api/v1/plugins/{plugin.id}/versions/{release.id}/download"
                    )
                    db.commit()
                    print(f"{market_id}: archived {release.version}")
                    continue
                client = RepositoryProvider(
                    provider, os.environ.get(f"{provider.upper()}_BACKFILL_TOKEN", "")
                )
                if provider == "github" and org not in orgs:
                    try:
                        orgs[org] = await client.public_github_repositories(org)
                    except HTTPException:
                        orgs[org] = {}
                repository = orgs.get(org, {}).get(
                    full_name.casefold()
                ) or await client.public_repository(full_name)
                current_archive = any(
                    release.package_sha256 and release.version == plugin.version
                    for release in plugin.versions
                )
                ref = plugin.commit_sha or await client.resolve_commit(
                    repository, repository.default_branch
                )
                documents, docs_failed = await client.documentation(repository, ref)
                archive_error = None
                if plugin.commit_sha and not current_archive:
                    try:
                        snapshot = await client.snapshot(repository, ref)
                        if (
                            f"{snapshot.metadata.author}/{snapshot.metadata.name}"
                            == market_id
                            and normalized_version(snapshot.metadata.version)
                            == normalized_version(plugin.version)
                        ):
                            await archive_snapshot(db, plugin, snapshot)
                    except (HTTPException, ValueError) as exc:
                        archive_error = str(exc)
                        failures += 1
                plugin.provider = provider
                plugin.stars = (
                    repository.stars if repository.stars is not None else plugin.stars
                )
                if not docs_failed or not plugin.documents:
                    plugin.documents = {
                        "ref": ref,
                        "items": {
                            key: doc.model_dump() for key, doc in documents.items()
                        },
                    }
                plugin.sync_state = (
                    "failed"
                    if docs_failed
                    else ("ready" if plugin.commit_sha else "repository")
                )
                db.commit()
                print(
                    f"{market_id}: {plugin.sync_state}"
                    + (f"; {archive_error}" if archive_error else "")
                )
            except (HTTPException, ValueError) as exc:
                db.rollback()
                if not archives_only:
                    plugin.sync_state = "failed"
                    db.commit()
                failures += 1
                detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                print(f"{market_id}: {detail}")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--archives-only", action="store_true")
    args = parser.parse_args()
    if args.offset < 0 or args.limit <= 0:
        parser.error("Offset must be nonnegative and limit must be positive")
    raise SystemExit(
        bool(
            asyncio.run(run(args.offset, args.limit, archives_only=args.archives_only))
        )
    )
