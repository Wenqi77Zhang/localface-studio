"""Configuration security tests."""

import pytest
from pydantic import ValidationError

from localface_studio.infrastructure.config import Settings


def test_default_host_is_loopback() -> None:
    assert Settings().host == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.8", "8.8.8.8"])
def test_non_loopback_host_is_rejected(host: str) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(host=host)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8188",
        "http://192.168.1.8:8188",
        "http://example.com:8188",
        "http://user:password@127.0.0.1:8188",
        "http://127.0.0.1:8188/path",
    ],
)
def test_comfyui_requires_an_explicit_loopback_origin(url: str) -> None:
    with pytest.raises(ValidationError, match="loopback HTTP origin"):
        Settings(comfyui_url=url)


def test_comfyui_ipv6_loopback_is_normalized() -> None:
    assert Settings(comfyui_url="http://[::1]:8188").comfyui_url == "http://[::1]:8188"
