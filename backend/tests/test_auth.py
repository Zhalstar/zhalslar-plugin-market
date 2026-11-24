"""Authentication API behavior."""

from fastapi.testclient import TestClient


def test_register_session_and_logout(client: TestClient) -> None:
    """A registered user receives a session and can log out.

    Args:
        client: Initialized API client.
    """
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "password": "correct-horse-42",
            "display_name": "Plugin Owner",
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "owner@example.com"
    assert client.get("/api/v1/auth/me").status_code == 200

    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_duplicate_registration_is_rejected(client: TestClient) -> None:
    """Email uniqueness is enforced without exposing stored credentials.

    Args:
        client: Initialized API client.
    """
    payload = {"email": "duplicate@example.com", "password": "password-1234"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_login_rejects_invalid_password(client: TestClient) -> None:
    """An incorrect password returns the generic unauthorized response.

    Args:
        client: Initialized API client.
    """
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "duplicate@example.com", "password": "wrong-password-1"},
    )
    assert response.status_code == 401
