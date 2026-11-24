"""Behavior of version archives and public publisher profiles."""

import asyncio
import hashlib
from io import BytesIO
from types import SimpleNamespace
from zipfile import BadZipFile, ZipFile

import httpx
import pytest
from fastapi import HTTPException
from PIL import Image

from app.api import plugins
from app.config import get_settings
from app.packages import store_package, validate_zip
from app.providers import PluginMetadata, RepositorySnapshot
from app.schemas import Document, RepositoryResponse


def test_publish_update_and_unlist(client, monkeypatch, tmp_path):
    """Publish only validated packages and preserve immutable older downloads."""
    repository = RepositoryResponse(
        provider="github",
        id="1",
        full_name="example/archives",
        name="archives",
        owner="example",
        url="https://github.com/example/archives",
        default_branch="main",
        private=False,
        can_push=True,
        stars=0,
    )
    metadata = {
        "author": "example",
        "name": "archives",
        "version": "1.0.0",
        "repo": repository.url,
        "desc": "Archive test",
        "astrbot_version": ">=4.0",
        "support_platforms": ["telegram"],
        "tags": ["tools"],
    }
    package_blocked = False
    requests = []
    monkeypatch.setattr(get_settings().storage, "packages_directory", tmp_path)

    class Provider:
        async def repository_by_id(self, repo_id):
            assert repo_id == "1"
            return repository

        async def snapshot(self, repo):
            return RepositorySnapshot(
                repo,
                metadata["version"][0] * 40,
                PluginMetadata.model_validate(metadata),
                metadata.copy(),
                "# Documentation",
                {"readme": Document(path="README.md", markdown="# Documentation")},
                False,
                None,
                "",
            )

    async def store(repository, sha):
        requests.append(sha)
        if package_blocked:
            raise HTTPException(
                status_code=413, detail="Plugin archive exceeds size limit"
            )
        body = sha.encode()
        digest = hashlib.sha256(body).hexdigest()
        (tmp_path / f"{digest}.zip").write_bytes(body)
        return digest, len(body)

    monkeypatch.setattr(plugins, "_linked_provider", lambda *_: Provider())
    monkeypatch.setattr(plugins, "store_package", store)
    user = client.post(
        "/api/v1/auth/register",
        json={
            "email": "archives@example.com",
            "password": "archive-test-42",
            "display_name": "Archive publisher",
        },
    ).json()
    try:
        data = {"provider": "github", "repository_id": "1"}
        response = client.post("/api/v1/plugins/publish", json=data)
        assert response.status_code == 201, response.text
        plugin = response.json()
        assert plugin["stars"] == 0 and plugin["support_platforms"] == ["telegram"]
        by_stars = client.get("/api/v1/plugins", params={"sort": "stars"}).json()
        assert by_stars["items"][0]["id"] == plugin["id"]
        assert plugin["tags"] == ["tools"] and plugin["astrbot_version"] == ">=4.0"
        assert plugin["publisher_avatar_url"] is None
        image = BytesIO()
        Image.new("RGB", (32, 32), "blue").save(image, format="PNG")
        avatar = client.post(
            "/api/v1/users/me/avatar",
            content=image.getvalue(),
            headers={"Content-Type": "image/png"},
        ).json()["avatar_url"]
        listing = client.get("/api/v1/plugins", params={"search": "archives"}).json()
        assert listing["items"][0]["publisher_avatar_url"] == avatar
        assert client.get(avatar).status_code == 200
        detail_path = f"/api/v1/plugins/{plugin['id']}"
        old_path = plugin["download_url"]
        assert client.get(old_path).content == b"1" * 40
        assert (
            client.get(detail_path).json()["documents"]["readme"]["markdown"]
            == "# Documentation"
        )
        market_entry = client.get("/market.json").json()["example/archives"]
        assert market_entry["download_url"].endswith(old_path)
        assert market_entry["stars"] == 0
        assert (
            client.post("/api/v1/plugins/publish", json=data).json()["download_url"]
            == old_path
        )
        assert requests == ["1" * 40]
        assert client.post(f"{detail_path}/check-update").status_code == 409
        metadata["version"] = "2.0.0"
        package_blocked = True
        assert client.post(f"{detail_path}/check-update").status_code == 413
        assert client.get(detail_path).json()["version"] == "1.0.0"
        package_blocked = False
        assert client.post(f"{detail_path}/check-update").status_code == 200
        assert [
            item["version"] for item in client.get(detail_path).json()["versions"]
        ] == ["2.0.0", "1.0.0"]
        assert client.get(old_path).content == b"1" * 40
        assert len(client.get(f"/api/v1/users/{user['id']}").json()["plugins"]) == 1
        assert client.post(f"{detail_path}/unpublish").status_code == 200
        assert client.get(old_path).status_code == 404
        assert not client.get(f"/api/v1/users/{user['id']}").json()["plugins"]
    finally:
        client.post("/api/v1/auth/logout")


def test_public_profile_and_avatar(client, monkeypatch):
    """Restrict profile writes to the owner and never expose private fields."""
    user = client.post(
        "/api/v1/auth/register",
        json={"email": "profiles@example.com", "password": "profile-test-42"},
    ).json()
    url = f"/api/v1/users/{user['id']}"
    try:
        assert (
            client.post("/api/v1/users/me", json={"display_name": "New name"}).json()[
                "display_name"
            ]
            == "New name"
        )
        assert client.get(url).json() == {
            "id": user["id"],
            "display_name": "New name",
            "avatar_url": None,
            "plugins": [],
        }
        assert (
            client.post(
                "/api/v1/users/me/avatar",
                content=b"<svg/>",
                headers={"content-type": "image/svg+xml"},
            ).status_code
            == 415
        )
        assert (
            client.post(
                "/api/v1/users/me/avatar",
                content=b"not png",
                headers={"content-type": "image/png"},
            ).status_code
            == 422
        )
        source = BytesIO()
        Image.new("RGB", (320, 180), "blue").save(source, "PNG")
        assert (
            client.post(
                "/api/v1/users/me/avatar",
                content=source.getvalue(),
                headers={"content-type": "image/png"},
            ).status_code
            == 200
        )
        avatar_response = client.get(client.get(url).json()["avatar_url"])
        assert avatar_response.headers["content-type"] == "image/webp"
        assert Image.open(BytesIO(avatar_response.content)).size == (256, 144)
        assert client.delete("/api/v1/users/me/avatar").json()["avatar_url"] is None
        assert client.get(f"{url}/avatar").status_code == 404
        monkeypatch.setattr(get_settings().market, "max_avatar_bytes", 1)
        assert (
            client.post(
                "/api/v1/users/me/avatar",
                content=b"12",
                headers={"content-type": "image/png"},
            ).status_code
            == 413
        )
    finally:
        client.post("/api/v1/auth/logout")
    assert client.get(url).status_code == 200
    assert (
        client.post(
            "/api/v1/users/me", json={"display_name": "Not the owner"}
        ).status_code
        == 401
    )


def test_zip_validation(tmp_path):
    """Check a normal provider ZIP and the size and path boundaries."""
    path = tmp_path / "plugin.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("plugin-abcd/metadata.yaml", "version: 1.0.0")
        archive.writestr("plugin-abcd/main.py", "")
    validate_zip(path, 1024)
    with pytest.raises(BadZipFile, match="size limit"):
        validate_zip(path, 3)
    with ZipFile(path, "a") as archive:
        archive.writestr("plugin-abcd/../escape.py", "")
    with pytest.raises(BadZipFile, match="unsafe"):
        validate_zip(path, 1024)


def test_signed_gitee_archive_stream(monkeypatch, tmp_path):
    """Enforce the compressed limit and accept only the expected signed redirect."""
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr(
            "plugin/metadata.yaml", "author: test\nname: plugin\nversion: 1.0.0"
        )
    body = content.getvalue()
    sha = "a" * 40
    target = f"https://gitee.com/test/plugin/repository/blazearchive/{sha}.zip?Signature=test"
    url_paths = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield body[:32]
            yield body[32:]

    def respond(request):
        url_paths.append(request.url.path)
        if "/archive/" in request.url.path:
            return httpx.Response(302, headers={"Location": target})
        return httpx.Response(200, stream=Chunks())

    client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.packages.httpx.AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )
    settings = get_settings()
    monkeypatch.setattr(settings.storage, "packages_directory", tmp_path)
    repository = SimpleNamespace(provider="gitee", full_name="test/plugin")
    digest, size = asyncio.run(
        store_package(repository, sha, expected_release=("test/plugin", "v1.0.0"))
    )
    assert size == len(body) and (tmp_path / f"{digest}.zip").read_bytes() == body
    assert len(url_paths) == 2

    with pytest.raises(HTTPException) as failure:
        asyncio.run(
            store_package(repository, sha, expected_release=("test/plugin", "2.0.0"))
        )
    assert failure.value.status_code == 422

    monkeypatch.setattr(settings.market, "max_package_bytes", len(body) - 1)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(store_package(repository, sha))
    assert failure.value.status_code == 413
    assert not list(tmp_path.glob("*.part"))

    target = target.replace("gitee.com", "example.com")
    with pytest.raises(HTTPException) as failure:
        asyncio.run(store_package(repository, sha))
    assert failure.value.status_code == 502
    assert "blazearchive" not in url_paths[-1]
