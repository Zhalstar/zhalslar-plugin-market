"""Fetch and validate immutable plugin ZIPs from supported repository hosts."""

from __future__ import annotations

import hashlib
import re
import stat
from contextlib import AsyncExitStack
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

import httpx
import yaml
from fastapi import HTTPException
from packaging.version import Version
from starlette.concurrency import run_in_threadpool

from .config import get_settings
from .schemas import RepositoryResponse


def validate_zip(
    path: Path, max_unpacked_bytes: int, expected_release: tuple[str, str] | None = None
) -> None:
    """Validate entry paths, expanded size, and CRCs without extracting files.

    Args:
        path: ZIP to validate.
        max_unpacked_bytes: Maximum total expanded size.
        expected_release: Optional market ID and version to verify against metadata.

    Raises:
        BadZipFile: If the ZIP or release metadata does not match expectations.
    """
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > 10_000:
            raise BadZipFile("Invalid ZIP entry count")
        if sum(item.file_size for item in entries) > max_unpacked_bytes:
            raise BadZipFile("Expanded ZIP exceeds size limit")
        roots = set()
        names = set()
        has_metadata = False
        for item in entries:
            name = item.orig_filename.rstrip("/")
            parts = name.split("/")
            if (
                any(
                    not part or part in {".", ".."} or part.rstrip(" .") != part
                    for part in parts
                )
                or any(char in name for char in ("\\", ":", "\x00"))
                or PurePosixPath(name).is_absolute()
                or stat.S_ISLNK(item.external_attr >> 16)
                or name.casefold() in names
                or (len(parts) == 1 and not item.is_dir())
            ):
                raise BadZipFile("ZIP has unsafe or ambiguous entries")
            roots.add(parts[0])
            names.add(name.casefold())
            has_metadata |= (
                len(parts) == 2 and parts[1] == "metadata.yaml" and not item.is_dir()
            )
        if len(roots) != 1 or not has_metadata or archive.testzip() is not None:
            raise BadZipFile("ZIP does not contain a valid repository archive")
        if expected_release is not None:
            item = archive.getinfo(f"{next(iter(roots))}/metadata.yaml")
            if item.file_size > 256 * 1024:
                raise BadZipFile("Plugin metadata is too large")
            market_id, version = expected_release
            try:
                metadata = yaml.safe_load(archive.read(item))
                same_release = (
                    isinstance(metadata, dict)
                    and f"{metadata.get('author')}/{metadata.get('name')}" == market_id
                    and Version(str(metadata.get("version"))) == Version(version)
                )
            except (yaml.YAMLError, ValueError, RecursionError) as exc:
                raise BadZipFile("Invalid plugin metadata") from exc
            if not same_release:
                raise BadZipFile("Archive metadata does not match the selected release")


async def store_package(
    repository: RepositoryResponse,
    sha: str,
    *,
    expected_release: tuple[str, str] | None = None,
) -> tuple[str, int]:
    """Stream a pinned repository ZIP into content-addressed persistent storage.

    Args:
        repository: Canonical repository and provider.
        sha: Full commit hash for the archive.
        expected_release: Optional market ID and version to verify against metadata.

    Returns:
        ZIP SHA-256 and compressed byte count.

    Raises:
        HTTPException: If a provider response or package is invalid.
    """
    settings = get_settings()
    parts = repository.full_name.split("/")
    if (
        len(parts) != 2
        or not all(
            re.fullmatch(r"[a-zA-Z0-9_.-]+", part) and part not in {".", ".."}
            for part in parts
        )
        or not re.fullmatch(r"[a-f0-9]{40}", sha)
    ):
        raise HTTPException(status_code=422, detail="Invalid repository or commit")
    name = "/".join(quote(part, safe="") for part in parts)
    url = (
        f"https://codeload.github.com/{name}/zip/{sha}"
        if repository.provider == "github"
        else f"https://gitee.com/{name}/repository/archive/{sha}.zip"
    )
    directory = settings.storage.packages_directory
    directory.mkdir(parents=True, exist_ok=True)
    limit = settings.market.max_package_bytes
    digest = hashlib.sha256()
    size = 0
    temp_path = None
    try:
        async with (
            httpx.AsyncClient(
                timeout=settings.market.request_timeout_seconds, follow_redirects=False
            ) as client,
            AsyncExitStack() as requests,
        ):
            headers = {"Accept-Encoding": "identity"}
            response = await requests.enter_async_context(
                client.stream("GET", url, headers=headers)
            )
            if repository.provider == "gitee" and response.is_redirect:
                target = response.url.join(response.headers.get("location", ""))
                if (
                    target.scheme != "https"
                    or target.host != "gitee.com"
                    or target.port not in {None, 443}
                    or target.userinfo
                    or target.path != f"/{name}/repository/blazearchive/{sha}.zip"
                ):
                    raise HTTPException(
                        status_code=502, detail="Unexpected Gitee archive redirect"
                    )
                await response.aclose()
                response = await requests.enter_async_context(
                    client.stream("GET", target, headers=headers)
                )
            response.raise_for_status()
            length = response.headers.get("content-length", "")
            if length.isdecimal() and int(length) > limit:
                raise HTTPException(
                    status_code=413, detail="Plugin archive exceeds size limit"
                )
            with NamedTemporaryFile(
                dir=directory, suffix=".part", delete=False
            ) as stream:
                temp_path = Path(stream.name)
                async for chunk in response.aiter_raw(chunk_size=65536):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(
                            status_code=413, detail="Plugin archive exceeds size limit"
                        )
                    digest.update(chunk)
                    stream.write(chunk)
        await run_in_threadpool(
            validate_zip,
            temp_path,
            settings.market.max_unpacked_bytes,
            expected_release,
        )
        checksum = digest.hexdigest()
        temp_path.replace(directory / f"{checksum}.zip")
        return checksum, size
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="Repository archive download failed"
        ) from exc
    except (BadZipFile, RuntimeError, NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid plugin archive") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
