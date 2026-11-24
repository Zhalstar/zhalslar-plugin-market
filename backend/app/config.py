"""Application configuration loaded from one YAML file."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?}")


class AppConfig(BaseModel):
    """Public application identity and URLs."""

    name: str = "ZhalHub"
    public_url: str = "http://localhost"
    frontend_url: str = "http://localhost"
    environment: str = "development"


class ServerConfig(BaseModel):
    """HTTP server and browser access settings."""

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost"])


class DatabaseConfig(BaseModel):
    """SQLAlchemy database connection settings."""

    url: str = "sqlite:///./data/market.db"


class AuthConfig(BaseModel):
    """Session and password authentication settings."""

    secret_key: str = "change-me-in-production"
    access_token_minutes: int = 30
    refresh_token_days: int = 30
    secure_cookies: bool = False
    require_email_verification: bool = False


class OAuthProviderConfig(BaseModel):
    """OAuth client credentials for one repository provider."""

    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    callback_url: str = ""


class OAuthConfig(BaseModel):
    """Supported repository provider OAuth settings."""

    encryption_key: str = ""
    github: OAuthProviderConfig = Field(default_factory=OAuthProviderConfig)
    gitee: OAuthProviderConfig = Field(default_factory=OAuthProviderConfig)


class EmailConfig(BaseModel):
    """SMTP settings reserved for verification and password reset email."""

    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 465
    username: str = ""
    password: str = ""
    from_address: str = ""


class StorageConfig(BaseModel):
    """Local persistent asset storage settings."""

    directory: Path = Path("./data/assets")
    packages_directory: Path = Path("./data/packages")
    public_path: str = "/plugin-assets"


class MarketConfig(BaseModel):
    """Marketplace policy and remote fetch limits."""

    title: str = "ZhalHub"
    description: str = "饰乐维护的 AstrBot 插件市场。"
    allow_github: bool = True
    allow_gitee: bool = True
    max_logo_bytes: int = 2 * 1024 * 1024
    max_readme_bytes: int = 1024 * 1024
    max_package_bytes: int = Field(default=16 * 1024 * 1024, gt=0)
    max_unpacked_bytes: int = Field(default=128 * 1024 * 1024, gt=0)
    max_avatar_bytes: int = Field(default=512 * 1024, gt=0)
    request_timeout_seconds: int = 15
    seed_file: Path = Path("./market.json")


class SecurityConfig(BaseModel):
    """Network and repository host restrictions."""

    allowed_repository_hosts: list[str] = Field(
        default_factory=lambda: ["github.com", "gitee.com"]
    )
    allowed_asset_hosts: list[str] = Field(
        default_factory=lambda: ["raw.githubusercontent.com", "gitee.com"]
    )


class Settings(BaseModel):
    """Complete application configuration."""

    app: AppConfig = Field(default_factory=AppConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    oauth: OAuthConfig = Field(default_factory=OAuthConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    market: MarketConfig = Field(default_factory=MarketConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
        """Reject unsafe secrets when production mode is enabled.

        Returns:
            The validated settings object.

        Raises:
            ValueError: If production uses a known development secret.
        """
        if (
            self.app.environment == "production"
            and self.auth.secret_key == "change-me-in-production"
        ):
            raise ValueError("AUTH_SECRET_KEY must be changed in production")
        return self


def _expand_environment(value: Any) -> Any:
    """Recursively replace `${NAME}` and `${NAME:-default}` placeholders.

    Args:
        value: YAML value to process.

    Returns:
        The value with environment placeholders expanded.
    """
    if isinstance(value, dict):
        return {key: _expand_environment(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_environment(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name, default = match.groups()
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise ValueError(f"Required environment variable is not set: {name}")

    return ENV_PATTERN.sub(replace, value)


@lru_cache
def get_settings() -> Settings:
    """Load and validate the configured YAML file.

    Returns:
        Validated application settings.

    Raises:
        FileNotFoundError: If the configured YAML file does not exist.
        ValueError: If YAML content or environment expansion is invalid.
    """
    default_path = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
    config_path = Path(os.getenv("MARKET_CONFIG", str(default_path)))
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Configuration root must be an object")
    settings = Settings.model_validate(_expand_environment(raw))
    project_root = config_path.resolve().parent.parent
    if not settings.market.seed_file.is_absolute():
        settings.market.seed_file = project_root / settings.market.seed_file
    if not settings.storage.directory.is_absolute():
        settings.storage.directory = project_root / settings.storage.directory
    if not settings.storage.packages_directory.is_absolute():
        settings.storage.packages_directory = (
            project_root / settings.storage.packages_directory
        )
    assets = settings.storage.directory.resolve()
    packages = settings.storage.packages_directory.resolve()
    if packages == assets or packages.is_relative_to(assets):
        raise ValueError("Package storage must be outside the public assets directory")
    return settings
