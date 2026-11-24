"""Validated API request and response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """Email registration payload."""

    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(default="", max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """Require passwords with letters and numbers.

        Args:
            value: Proposed password.

        Returns:
            The validated password.

        Raises:
            ValueError: If the password lacks letters or numbers.
        """
        if not any(character.isalpha() for character in value) or not any(
            character.isdigit() for character in value
        ):
            raise ValueError("Password must contain letters and numbers")
        return value


class LoginRequest(BaseModel):
    """Email login payload."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Safe public view of the current user."""

    id: str
    email: str
    display_name: str
    avatar_url: str | None
    email_verified: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RepositoryResponse(BaseModel):
    """Repository available through a linked account."""

    provider: str
    id: str
    full_name: str
    name: str
    owner: str
    url: str
    default_branch: str
    private: bool
    can_push: bool
    stars: int | None = None


class PublishPluginRequest(BaseModel):
    """Request to publish a linked repository."""

    provider: str
    repository_id: str


class ClaimPluginsRequest(BaseModel):
    """Marketplace plugin IDs to claim together."""

    plugin_ids: list[str] = Field(min_length=1, max_length=100)


class PluginResponse(BaseModel):
    """Frontend marketplace plugin representation."""

    id: str
    market_id: str
    author: str
    name: str
    display_name: str
    version: str
    repo: str
    desc: str
    short_desc: str
    logo: str
    download_url: str
    provider: str | None
    owner_id: str | None
    publisher_avatar_url: str | None
    stars: int | None
    astrbot_version: str
    support_platforms: list[str]
    tags: list[str]
    status: str
    created_at: datetime
    updated_at: datetime


class PluginPage(BaseModel):
    """One page of plugin results and the total matching count."""

    items: list[PluginResponse]
    total: int


class Document(BaseModel):
    """Markdown source and its location in a fixed repository revision."""

    path: str
    markdown: str


class PluginVersionResponse(BaseModel):
    """Published version and optional downloadable archive."""

    version: str
    commit_sha: str
    published_at: datetime
    download_url: str | None
    package_bytes: int | None
    package_sha256: str | None


class PluginDetailResponse(PluginResponse):
    """Detailed plugin view, including documents and version history."""

    publisher_name: str | None
    sync_state: str
    docs_ref: str
    documents: dict[str, Document]
    versions: list[PluginVersionResponse]


class PublicUserResponse(BaseModel):
    """Only public fields returned to marketplace visitors."""

    id: str
    display_name: str
    avatar_url: str | None
    plugins: list[PluginResponse]


class OAuthAccountResponse(BaseModel):
    """Linked repository account without credentials."""

    provider: str
    username: str
    created_at: datetime


class MessageResponse(BaseModel):
    """Simple API operation result."""

    message: str
