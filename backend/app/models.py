"""Persistent marketplace entities."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Return an aware UTC timestamp.

    Returns:
        Current time in UTC.
    """
    return datetime.now(timezone.utc)


def new_id() -> str:
    """Generate a stable string UUID.

    Returns:
        A random UUID string.
    """
    return str(uuid.uuid4())


class User(Base):
    """Marketplace user authenticated by email and password."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(100), default="")
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    avatar_revision: Mapped[str | None] = mapped_column(String(36))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    plugins: Mapped[list[Plugin]] = relationship(back_populates="owner")

    @property
    def avatar_url(self) -> str | None:
        """Return the public avatar URL for the current image."""
        if self.avatar_revision:
            return f"/api/v1/users/{self.id}/avatar?v={self.avatar_revision}"
        return None


class OAuthAccount(Base):
    """Encrypted OAuth connection to a repository provider."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id"),
        UniqueConstraint("user_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    provider_user_id: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(String(200))
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="oauth_accounts")


class Plugin(Base):
    """Published plugin and its current repository snapshot."""

    __tablename__ = "plugins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    market_id: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider_repo_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    repo_full_name: Mapped[str] = mapped_column(String(300), default="")
    repo_url: Mapped[str] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(200), default="main")
    commit_sha: Mapped[str] = mapped_column(String(100), default="")
    author: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    short_description: Mapped[str] = mapped_column(Text, default="")
    logo_url: Mapped[str] = mapped_column(String(1000), default="")
    readme: Mapped[str] = mapped_column(Text, default="")
    stars: Mapped[int | None] = mapped_column(Integer)
    documents: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sync_state: Mapped[str | None] = mapped_column(String(20))
    download_url: Mapped[str] = mapped_column(String(1000), default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="published", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    owner: Mapped[User | None] = relationship(back_populates="plugins")
    versions: Mapped[list[PluginVersion]] = relationship(
        back_populates="plugin", cascade="all, delete-orphan"
    )


class PluginVersion(Base):
    """Immutable plugin version metadata snapshot."""

    __tablename__ = "plugin_versions"
    __table_args__ = (UniqueConstraint("plugin_id", "version", "commit_sha"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id", ondelete="CASCADE"))
    version: Mapped[str] = mapped_column(String(100))
    commit_sha: Mapped[str] = mapped_column(String(100), default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    package_sha256: Mapped[str | None] = mapped_column(String(64))
    package_bytes: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    plugin: Mapped[Plugin] = relationship(back_populates="versions")


class RefreshToken(Base):
    """Revocable hashed browser refresh token."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
