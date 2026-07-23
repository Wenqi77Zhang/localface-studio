"""Validated runtime configuration with privacy-safe defaults."""

from functools import lru_cache
from ipaddress import ip_address
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from LOCALFACE_ environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="LOCALFACE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("host")
    @classmethod
    def require_loopback(cls, value: str) -> str:
        """Reject LAN and public bindings until a separate security review exists."""
        address = ip_address(value)
        if not address.is_loopback:
            raise ValueError("host must be an IPv4 or IPv6 loopback address")
        return address.compressed


@lru_cache
def get_settings() -> Settings:
    """Load and cache immutable process settings."""
    return Settings()
