"""Marketplace compatibility behavior."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.market import market_record, normalized_version
from app.models import Plugin


def test_legacy_market_is_seeded(client: TestClient) -> None:
    """The existing static market is imported on the first startup.

    Args:
        client: Initialized API client.
    """
    response = client.get("/market.json")
    assert response.status_code == 200
    document = response.json()
    assert document["$meta"]["schema_version"] == 1
    assert len(document) == 47
    assert "饰乐/astrbot_plugin_afdian" in document


def test_market_md5_matches_response_bytes(client: TestClient) -> None:
    """The compatibility fingerprint hashes the exact JSON response.

    Args:
        client: Initialized API client.
    """
    market_response = client.get("/market.json")
    digest_response = client.get("/market-md5.json")
    expected = hashlib.md5(market_response.content, usedforsecurity=False).hexdigest()
    assert digest_response.json() == {"md5": expected}


@pytest.mark.parametrize("stars", [29, 0, None])
def test_market_exports_stored_repository_stars(stars: int | None) -> None:
    """Use the stored count, including zero, instead of authored metadata.

    Args:
        stars: Stored repository star count or None if unavailable.
    """
    record = market_record(
        Plugin(metadata_json={"stars": 99}, logo_url="", download_url="", stars=stars)
    )
    if stars is None:
        assert "stars" not in record
    else:
        assert record["stars"] == stars


def test_version_parser_accepts_v_prefix() -> None:
    """Manual update comparison accepts common leading-v versions."""
    assert normalized_version("v2.1.0") > normalized_version("2.0.9")


def test_market_pagination_and_search(client: TestClient) -> None:
    """Pages contain distinct results and totals respect active filters."""
    first = client.get("/api/v1/plugins").json()
    second = client.get("/api/v1/plugins", params={"page": 2}).json()
    last = client.get("/api/v1/plugins", params={"page": 6}).json()
    assert first["total"] == second["total"] == last["total"] == 46
    assert len(first["items"]) == len(second["items"]) == 9
    assert len(last["items"]) == 1
    assert {item["id"] for item in first["items"]}.isdisjoint(
        item["id"] for item in second["items"]
    )
    search = client.get("/api/v1/plugins", params={"search": "afdian"}).json()
    assert search["total"] == 1
    assert search["items"][0]["name"] == "astrbot_plugin_afdian"
    for size in (18, 27, 0):
        batch = client.get("/api/v1/plugins", params={"page_size": size}).json()
        assert len(batch["items"]) == (size or 46)
        assert batch["total"] == 46
    assert client.get("/api/v1/plugins", params={"page_size": -1}).status_code == 422


def test_market_sort_applies_before_pagination(client: TestClient) -> None:
    """Ordering remains consistent across pages and invalid sorts are rejected."""
    for mode, key, reverse in (
        ("name", lambda item: (item["display_name"] or item["name"]).lower(), False),
        ("newest", lambda item: item["created_at"], True),
        ("updated", lambda item: item["updated_at"], True),
    ):
        ordered = client.get(
            "/api/v1/plugins", params={"sort": mode, "page_size": 0}
        ).json()["items"]
        assert [key(item) for item in ordered] == sorted(
            map(key, ordered), reverse=reverse
        )
        part = client.get("/api/v1/plugins", params={"sort": mode, "page": 2}).json()[
            "items"
        ]
        assert part == ordered[9:18]
    assert client.get("/api/v1/plugins", params={"sort": "invalid"}).status_code == 422
