"""GitHub and Gitee repository provider integrations."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx
import yaml
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import OAuthProviderConfig, get_settings
from .schemas import Document, RepositoryResponse


class PluginMetadata(BaseModel):
    """Required and optional AstrBot plugin metadata."""

    model_config = ConfigDict(extra="allow")

    author: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=500)
    desc: str = Field(min_length=1)
    display_name: str = ""
    short_desc: str = ""
    download_url: str = ""
    logo: str = ""

    @field_validator("author", "name")
    @classmethod
    def reject_slashes(cls, value: str) -> str:
        """Reject identifiers that cannot form a market ID.

        Args:
            value: Identifier component.

        Returns:
            Trimmed identifier.

        Raises:
            ValueError: If the value contains a slash.
        """
        value = value.strip()
        if "/" in value:
            raise ValueError("Plugin author and name cannot contain slashes")
        return value


@dataclass
class RepositorySnapshot:
    """Repository files and metadata used to publish one version."""

    repository: RepositoryResponse
    commit_sha: str
    metadata: PluginMetadata
    metadata_raw: dict[str, Any]
    readme: str
    documents: dict[str, Document]
    docs_failed: bool
    logo_bytes: bytes | None
    logo_url: str


class RepositoryProvider:
    """Provider-neutral GitHub and Gitee API client."""

    def __init__(self, provider: str, access_token: str) -> None:
        """Initialize a provider client.

        Args:
            provider: `github` or `gitee`.
            access_token: OAuth access token.

        Raises:
            HTTPException: If the provider is unsupported.
        """
        if provider not in {"github", "gitee"}:
            raise HTTPException(status_code=400, detail="Unsupported provider")
        self.provider = provider
        self.access_token = access_token
        self.settings = get_settings()
        self.timeout = self.settings.market.request_timeout_seconds

    def _headers(self) -> dict[str, str]:
        """Build provider request headers.

        Returns:
            HTTP request headers.
        """
        if self.provider == "github":
            return {
                **(
                    {"Authorization": f"Bearer {self.access_token}"}
                    if self.access_token
                    else {}
                ),
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "zhalslar-plugin-market",
            }
        return {"Accept": "application/json", "User-Agent": "zhalslar-plugin-market"}

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build provider query parameters.

        Args:
            extra: Additional query parameters.

        Returns:
            Provider query parameters.
        """
        params = dict(extra or {})
        if self.provider == "gitee" and self.access_token:
            params["access_token"] = self.access_token
        return params

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch JSON from a fixed provider API host.

        Args:
            url: Provider API URL created by this module.
            params: Optional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            HTTPException: If the provider request fails.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    headers=self._headers(),
                    params=self._params(params),
                    follow_redirects=False,
                )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            code = 404 if exc.response.status_code == 404 else 502
            raise HTTPException(
                status_code=code, detail=f"{self.provider.title()} request failed"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=502, detail=f"{self.provider.title()} request failed"
            ) from exc

    async def current_identity(self) -> dict[str, Any]:
        """Fetch the linked provider identity.

        Returns:
            Provider user object.
        """
        url = (
            "https://api.github.com/user"
            if self.provider == "github"
            else "https://gitee.com/api/v5/user"
        )
        return await self._get(url)

    async def list_repositories(self) -> list[RepositoryResponse]:
        """List original public repositories controlled by the linked account.

        Returns:
            Normalized repository list.
        """
        url = (
            "https://api.github.com/user/repos"
            if self.provider == "github"
            else "https://gitee.com/api/v5/user/repos"
        )
        identity = await self.current_identity()
        user_id = str(identity.get("id") or "")
        if not user_id:
            raise HTTPException(status_code=502, detail="Invalid provider identity")
        items = []
        page = 1
        while True:
            batch = await self._get(
                url,
                {
                    "per_page": 100,
                    "sort": "updated",
                    "visibility": "public",
                    "page": page,
                },
            )
            items.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        repositories = []
        for item in items:
            if (
                item.get("private") is not False
                or item.get("fork") is not False
                or item.get("internal") is True
                or item.get("visibility", "public") != "public"
            ):
                continue
            owner = item.get("owner") or {}
            full_name = str(
                item.get("full_name") or item.get("path_with_namespace") or ""
            )
            if not item.get("id") or not re.fullmatch(r"[\w.-]+/[\w.-]+", full_name):
                continue
            owner_type = owner.get("type")
            if self.provider == "gitee":
                # Gitee may expose a personal user as the owner of a group repository.
                namespace = item.get("namespace") or {}
                owner_type = {
                    "personal": "User",
                    "group": "Organization",
                    "organization": "Organization",
                    "enterprise": "Organization",
                }.get(namespace.get("type"))
            allowed = (
                owner_type == "User"
                and user_id == str(owner.get("id") or "")
                and full_name.split("/", 1)[0].casefold()
                == str(owner.get("login") or "").casefold()
            ) or (
                owner_type == "Organization"
                and (
                    (item.get("permissions") or {}).get("admin") is True
                    or (item.get("permission") or {}).get("admin") is True
                )
            )
            if not allowed:
                continue
            host = "github.com" if self.provider == "github" else "gitee.com"
            repositories.append(
                RepositoryResponse(
                    provider=self.provider,
                    id=str(item["id"]),
                    full_name=full_name,
                    name=str(item["name"]),
                    owner=str(owner.get("login") or owner.get("name") or ""),
                    url=f"https://{host}/{full_name}",
                    default_branch=str(item.get("default_branch") or "main"),
                    private=False,
                    can_push=True,
                    stars=item.get("stargazers_count"),
                )
            )
        return repositories

    async def repository_by_id(self, repository_id: str) -> RepositoryResponse:
        """Resolve a repository ID from the linked user's allowed repositories.

        Args:
            repository_id: Provider repository ID.

        Returns:
            Matching public repository owned or administered by the linked account.

        Raises:
            HTTPException: If the repository is absent or not writable.
        """
        repository = next(
            (
                item
                for item in await self.list_repositories()
                if item.id == repository_id
            ),
            None,
        )
        if repository is None or repository.private or not repository.can_push:
            raise HTTPException(
                status_code=403, detail="Repository is not publishable by this account"
            )
        return repository

    async def _repository_blob(
        self,
        repository: RepositoryResponse,
        path: str,
        ref: str,
        *,
        required: bool = False,
    ) -> bytes | None:
        """Read one repository file through the provider API.

        Args:
            repository: Validated repository.
            path: Root-relative file name.
            required: Whether a provider error must fail the operation.

        Returns:
            Decoded file bytes, or None when an optional file is absent.
        """
        if self.provider == "github" and not self.access_token:
            name = "/".join(
                quote(part, safe="") for part in repository.full_name.split("/")
            )
            raw_url = f"https://raw.githubusercontent.com/{name}/{ref}/{path}"
            limit = max(
                self.settings.market.max_logo_bytes,
                self.settings.market.max_readme_bytes,
                256 * 1024,
            )
            try:
                async with (
                    httpx.AsyncClient(timeout=self.timeout) as client,
                    client.stream("GET", raw_url, follow_redirects=False) as response,
                ):
                    if response.status_code == 404 and not required:
                        return None
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > limit:
                            raise HTTPException(
                                status_code=422, detail=f"{path} exceeds size limit"
                            )
                        body.extend(chunk)
                    return bytes(body)
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502, detail=f"Cannot fetch {path}"
                ) from exc
        full_name = "/".join(
            quote(part, safe="") for part in repository.full_name.split("/")
        )
        api = (
            "https://api.github.com"
            if self.provider == "github"
            else "https://gitee.com/api/v5"
        )
        url = f"{api}/repos/{full_name}/contents/{path}"
        try:
            payload = await self._get(url, {"ref": ref})
        except HTTPException as exc:
            if not required and exc.status_code == 404:
                return None
            raise
        content = str(payload.get("content") or "").replace("\n", "")
        if not content:
            return None
        try:
            return base64.b64decode(content)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=f"Cannot decode {path}"
            ) from exc

    async def _repository_file(
        self,
        repository: RepositoryResponse,
        path: str,
        ref: str,
        *,
        required: bool = False,
    ) -> str | None:
        """Read one UTF-8 repository file through the provider API.

        Args:
            repository: Validated repository.
            path: Root-relative file name.
            required: Whether a provider error must fail the operation.

        Returns:
            UTF-8 file content, or None when an optional file is absent.

        Raises:
            HTTPException: If the repository file is not valid UTF-8.
        """
        content = await self._repository_blob(repository, path, ref, required=required)
        if content is None:
            return None
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=422, detail=f"Cannot decode {path}"
            ) from exc

    async def public_repository(self, full_name: str) -> RepositoryResponse:
        """Read the canonical public repository for a historical market entry."""
        owner, name = full_name.split("/", 1)
        api = (
            "https://api.github.com"
            if self.provider == "github"
            else "https://gitee.com/api/v5"
        )
        data = await self._get(
            f"{api}/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        )
        if data.get("private"):
            raise HTTPException(status_code=403, detail="Repository is private")
        return RepositoryResponse(
            provider=self.provider,
            id=str(data["id"]),
            full_name=data["full_name"],
            name=data["name"],
            owner=owner,
            url=data["html_url"],
            default_branch=data.get("default_branch") or "main",
            private=False,
            can_push=False,
            stars=data.get("stargazers_count"),
        )

    async def public_github_repositories(
        self, owner: str
    ) -> dict[str, RepositoryResponse]:
        """Read a page of public repository details in a single REST request."""
        slug = quote(owner, safe="")
        try:
            repos = await self._get(
                f"https://api.github.com/orgs/{slug}/repos",
                {"type": "public", "per_page": 100},
            )
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            repos = await self._get(
                f"https://api.github.com/users/{slug}/repos",
                {"type": "owner", "per_page": 100},
            )
        return {
            data["full_name"].casefold(): RepositoryResponse(
                provider="github",
                id=str(data["id"]),
                full_name=data["full_name"],
                name=data["name"],
                owner=owner,
                url=data["html_url"],
                default_branch=data.get("default_branch") or "main",
                private=False,
                can_push=False,
                stars=data.get("stargazers_count"),
            )
            for data in repos
            if not data.get("private")
        }

    async def resolve_commit(self, repository: RepositoryResponse, ref: str) -> str:
        """Resolve a branch or tag to its full commit ID."""
        api = (
            "https://api.github.com"
            if self.provider == "github"
            else "https://gitee.com/api/v5"
        )
        full_name = "/".join(
            quote(part, safe="") for part in repository.full_name.split("/")
        )
        commit = await self._get(
            f"{api}/repos/{full_name}/commits/{quote(ref, safe='')}"
        )
        sha = str(commit.get("sha") or commit.get("id") or "")
        if not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise HTTPException(status_code=502, detail="Repository commit is invalid")
        return sha

    async def snapshot(
        self, repository: RepositoryResponse, ref: str | None = None
    ) -> RepositorySnapshot:
        """Read and validate the current repository plugin snapshot.

        Args:
            repository: Validated public repository.
            ref: Optional known commit to restore.

        Returns:
            Validated repository snapshot.

        Raises:
            HTTPException: If required metadata is missing or invalid.
        """
        ref = ref or await self.resolve_commit(repository, repository.default_branch)
        if not re.fullmatch(r"[a-f0-9]{40}", ref):
            raise HTTPException(status_code=502, detail="Repository commit is invalid")
        metadata_text = await self._repository_file(
            repository, "metadata.yaml", ref, required=True
        )
        if metadata_text is None:
            raise HTTPException(status_code=422, detail="metadata.yaml is required")
        if len(metadata_text.encode()) > 256 * 1024:
            raise HTTPException(status_code=422, detail="metadata.yaml is too large")
        try:
            metadata_raw = yaml.safe_load(metadata_text) or {}
            if not isinstance(metadata_raw, dict):
                raise ValueError("Metadata root is not an object")
            metadata = PluginMetadata.model_validate(metadata_raw)
        except (ValueError, RecursionError, yaml.YAMLError) as exc:
            raise HTTPException(
                status_code=422, detail="Invalid metadata.yaml"
            ) from exc

        normalized_repo = metadata.repo.rstrip("/").removesuffix(".git").casefold()
        if (
            normalized_repo
            != repository.url.rstrip("/").removesuffix(".git").casefold()
        ):
            raise HTTPException(
                status_code=422,
                detail="metadata.yaml repo must match the linked repository",
            )

        documents, docs_failed = await self.documentation(repository, ref)
        try:
            logo = await self._repository_blob(repository, "logo.png", ref)
        except HTTPException:
            logo = None
        if logo and (
            len(logo) > self.settings.market.max_logo_bytes
            or not logo.startswith(b"\x89PNG\r\n\x1a\n")
        ):
            logo = None
        return RepositorySnapshot(
            repository=repository,
            commit_sha=ref,
            metadata=metadata,
            metadata_raw=metadata_raw,
            readme=documents["readme"].markdown if "readme" in documents else "",
            documents=documents,
            docs_failed=docs_failed,
            logo_bytes=logo,
            logo_url=metadata.logo,
        )

    async def documentation(
        self, repository: RepositoryResponse, ref: str
    ) -> tuple[dict[str, Document], bool]:
        """Read Markdown files and distinguish absence from fetch failures.

        Args:
            repository: Validated public repository.
            ref: Fixed repository commit.

        Returns:
            Available documents and whether any fetch failed.
        """
        documents: dict[str, Document] = {}
        docs_failed = False
        files: dict[str, str] | None = None
        if self.provider == "github":
            full_name = "/".join(
                quote(part, safe="") for part in repository.full_name.split("/")
            )
            tree_url = f"https://api.github.com/repos/{full_name}/git/trees"
            try:
                tree = await self._get(
                    f"{tree_url}/{quote(ref, safe='')}",
                    {"recursive": "1"},
                )
                if not tree["truncated"]:
                    files = {
                        item["path"].casefold(): item["path"]
                        for item in tree["tree"]
                        if item["type"] == "blob"
                    }
            except HTTPException:
                # A tree lookup is optional; individual files can still be readable.
                pass
        for key, paths in {
            "readme": ("README.md", "readme.md", "README.MD", "README"),
            "guide": ("docs/README.md", "docs/index.md"),
            "changelog": (
                "CHANGELOG.md",
                "changelog.md",
                "CHANGES.md",
                "CHANGELOG",
                "docs/CHANGELOG.md",
            ),
        }.items():
            if files is not None:
                paths = tuple(
                    dict.fromkeys(
                        files[path.casefold()]
                        for path in paths
                        if path.casefold() in files
                    )
                )
            for path in paths:
                try:
                    text = await self._repository_file(repository, path, ref)
                except HTTPException:
                    docs_failed = True
                    break
                if text:
                    if len(text.encode()) > self.settings.market.max_readme_bytes:
                        docs_failed = True
                    else:
                        documents[key] = Document(path=path, markdown=text)
                    break

        return documents, docs_failed


def provider_config(provider: str) -> OAuthProviderConfig:
    """Resolve enabled OAuth settings for a provider.

    Args:
        provider: Provider identifier.

    Returns:
        Provider OAuth settings.

    Raises:
        HTTPException: If the provider is disabled or unknown.
    """
    settings = get_settings()
    if provider not in {"github", "gitee"}:
        raise HTTPException(status_code=404, detail="Unknown provider")
    config = getattr(settings.oauth, provider)
    allowed = (
        settings.market.allow_github
        if provider == "github"
        else settings.market.allow_gitee
    )
    if (
        not allowed
        or not config.enabled
        or not config.client_id
        or not config.client_secret
    ):
        raise HTTPException(
            status_code=503, detail=f"{provider.title()} is not configured"
        )
    return config


def oauth_authorize_url(provider: str, state: str) -> str:
    """Build the external OAuth authorization URL.

    Args:
        provider: Provider identifier.
        state: Signed callback state.

    Returns:
        Provider authorization URL.
    """
    config = provider_config(provider)
    if provider == "github":
        base = "https://github.com/login/oauth/authorize"
        params = {
            "client_id": config.client_id,
            "redirect_uri": config.callback_url,
            "scope": "read:user",
            "state": state,
        }
    else:
        base = "https://gitee.com/oauth/authorize"
        params = {
            "client_id": config.client_id,
            "redirect_uri": config.callback_url,
            "response_type": "code",
            "scope": "user_info projects",
            "state": state,
        }
    return f"{base}?{urlencode(params)}"


async def exchange_oauth_code(provider: str, code: str) -> str:
    """Exchange an OAuth callback code for an access token.

    Args:
        provider: Provider identifier.
        code: One-time OAuth callback code.

    Returns:
        Provider access token.

    Raises:
        HTTPException: If the provider rejects the code.
    """
    config = provider_config(provider)
    if provider == "github":
        url = "https://github.com/login/oauth/access_token"
        payload = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
            "redirect_uri": config.callback_url,
        }
    else:
        url = "https://gitee.com/oauth/token"
        payload = {
            "grant_type": "authorization_code",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
            "redirect_uri": config.callback_url,
        }
    try:
        async with httpx.AsyncClient(
            timeout=get_settings().market.request_timeout_seconds
        ) as client:
            response = await client.post(
                url, data=payload, headers={"Accept": "application/json"}
            )
        response.raise_for_status()
        token = str(response.json().get("access_token") or "")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="OAuth exchange failed") from exc
    if not token:
        raise HTTPException(status_code=502, detail="OAuth provider returned no token")
    return token
