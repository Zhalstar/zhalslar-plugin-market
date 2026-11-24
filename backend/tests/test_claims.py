"""Repository authorization and ownership-only claim behavior."""

import asyncio

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import oauth
from app.config import get_settings
from app.database import SessionLocal
from app.models import OAuthAccount, Plugin, User
from app.providers import RepositoryProvider
from app.security import create_oauth_state, encrypt_oauth_token


@pytest.mark.parametrize("provider", ["github", "gitee"])
def test_only_owners_and_org_admins_can_publish_or_claim(provider, monkeypatch):
    """Deny personal collaborators, org writers, forks and non-public repositories."""
    personal = {"id": 42, "login": "owner", "type": "User"}
    other = {"id": 17, "login": "other", "type": "User"}
    org = {"id": 16, "login": "org", "type": "Organization"}
    items = [
        {
            "id": 1,
            "owner": personal,
            "full_name": "owner/original",
            "namespace": {"type": "personal"},
        },
        {
            "id": 2,
            "owner": other,
            "full_name": "other/shared",
            "namespace": {"type": "personal"},
            "permissions": {"admin": True},
        },
        {
            "id": 3,
            "owner": org if provider == "github" else personal,
            "full_name": "org/managed",
            "namespace": {"type": "group"},
            "permissions": {"admin": True},
        },
        {
            "id": 4,
            "owner": org if provider == "github" else personal,
            "full_name": "org/writable",
            "namespace": {"type": "group"},
            "permission": {"push": True},
        },
        {
            "id": 5,
            "owner": personal,
            "full_name": "owner/fork",
            "namespace": {"type": "personal"},
            "fork": True,
        },
        {
            "id": 6,
            "owner": personal,
            "full_name": "owner/private",
            "namespace": {"type": "personal"},
            "private": True,
        },
    ]

    async def get(_self, url, params=None):
        if url.endswith("/user"):
            return personal
        assert params["page"] == 1
        return [
            {"private": False, "fork": False, "name": "plugin", **item}
            for item in items
        ]

    monkeypatch.setattr(RepositoryProvider, "_get", get)
    client = RepositoryProvider(provider, "fake-token")
    assert [item.id for item in asyncio.run(client.list_repositories())] == ["1", "3"]
    with pytest.raises(HTTPException) as denied:
        asyncio.run(client.repository_by_id("4"))
    assert denied.value.status_code == 403


def test_claim_rechecks_permissions_and_preserves_market_record(client, monkeypatch):
    """Require the original repository and preserve the imported release and feed."""
    monkeypatch.setattr(
        get_settings().oauth, "encryption_key", Fernet.generate_key().decode()
    )
    api = TestClient(client.app)
    user = api.post(
        "/api/v1/auth/register",
        json={
            "email": "claim-owner@example.com",
            "password": "claim-test-42",
            "display_name": "Claim Owner",
        },
    ).json()
    with SessionLocal() as db:
        db.add(
            OAuthAccount(
                user_id=user["id"],
                provider="github",
                provider_user_id="42",
                username="Zhalstar",
                access_token_encrypted=encrypt_oauth_token("fake-token"),
            )
        )
        db.commit()
    plugin = api.get("/api/v1/plugins", params={"search": "afdian"}).json()["items"][0]
    target_id = plugin["id"]
    detail_url = f"/api/v1/plugins/{target_id}"
    previous = api.get(detail_url).json()
    feed = api.get("/market.json").content
    repo = {
        "id": 42,
        "full_name": "Zhalstar/astrbot_plugin_afdian",
        "name": "astrbot_plugin_afdian",
        "private": False,
        "fork": False,
        "owner": {"id": 42, "login": "Zhalstar", "type": "User"},
    }

    async def get(_self, url, params=None):
        return {"id": 42} if url.endswith("/user") else [repo]

    monkeypatch.setattr(RepositoryProvider, "_get", get)
    assert [item["id"] for item in api.get("/api/v1/plugins/claimable").json()] == [
        target_id
    ]
    published = api.post(
        "/api/v1/plugins/publish", json={"provider": "github", "repository_id": "42"}
    )
    assert published.status_code == 409
    assert published.json()["detail"] == "Claim this plugin before publishing"
    repo["owner"]["id"] = 43
    assert (
        api.post("/api/v1/plugins/claim", json={"plugin_ids": [target_id]}).status_code
        == 403
    )
    repo["owner"]["id"] = 42
    result = api.post("/api/v1/plugins/claim", json={"plugin_ids": [target_id]})
    assert result.status_code == 200, result.text
    assert result.json()[0]["owner_id"] == user["id"]
    assert api.get("/api/v1/plugins/claimable").json() == []
    assert (
        api.post("/api/v1/plugins/claim", json={"plugin_ids": [target_id]}).status_code
        == 409
    )
    actual = api.get(detail_url).json()
    assert actual["publisher_name"] == "Claim Owner"
    for field in (
        "version",
        "versions",
        "documents",
        "status",
        "download_url",
        "updated_at",
    ):
        assert actual[field] == previous[field]
    assert api.get("/market.json").content == feed
    with SessionLocal() as db:
        assert db.get(Plugin, target_id).provider_repo_id == "42"


def test_oauth_state_must_match_the_current_market_account(client, monkeypatch):
    """Reject cross-account callbacks before exchanging an OAuth code."""
    api = TestClient(client.app)
    api.post(
        "/api/v1/auth/register",
        json={"email": "oauth-client@example.com", "password": "oauth-test-42"},
    )
    state = create_oauth_state(User(id="another-market-account"), "github")

    async def unexpected(*_args):
        pytest.fail("An unrelated session must not exchange the OAuth code")

    monkeypatch.setattr(oauth, "exchange_oauth_code", unexpected)
    assert (
        api.get(
            "/api/v1/oauth/github/callback", params={"code": "fake", "state": state}
        ).status_code
        == 403
    )
