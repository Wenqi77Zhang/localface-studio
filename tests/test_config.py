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
