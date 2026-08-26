"""Validated runtime configuration with privacy-safe defaults."""

from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
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
    frontend_port: int = Field(default=5173, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    runtime_directory: Path = Path("runtime")
    workflow_backend: Literal["comfyui", "native-research", "simulation"] = "simulation"
    task_timeout_seconds: int = Field(default=300, ge=30, le=1800)
    comfyui_url: str = "http://127.0.0.1:8188"
    comfyui_workflow_path: Path = Path("config/comfyui-workflow.json")
    comfyui_input_directory: Path | None = None
    comfyui_output_directory: Path | None = None

    @field_validator("host")
    @classmethod
    def require_loopback(cls, value: str) -> str:
        """Reject LAN and public bindings until a separate security review exists."""
        address = ip_address(value)
        if not address.is_loopback:
            raise ValueError("host must be an IPv4 or IPv6 loopback address")
        return address.compressed

    @field_validator("comfyui_url")
    @classmethod
    def require_loopback_comfyui(cls, value: str) -> str:
        """Keep optional workflow traffic on an unauthenticated local boundary."""
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        try:
            loopback = parsed.hostname is not None and ip_address(parsed.hostname).is_loopback
        except ValueError:
            loopback = False
        if (
            parsed.scheme != "http"
            or parsed.hostname is None
            or not loopback
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or parsed.port is None
        ):
            raise ValueError("ComfyUI URL must be an explicit loopback HTTP origin")
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        return f"http://{host}:{parsed.port}"


@lru_cache
def get_settings() -> Settings:
    """Load and cache immutable process settings."""
    return Settings()
