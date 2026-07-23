"""Structured log redaction tests."""

import json
import logging

from localface_studio.infrastructure.logging import PrivacyJsonFormatter


def test_formatter_redacts_paths_secrets_and_unknown_fields() -> None:
    token = "ghp" + "_examplecredential"
    record = logging.LogRecord(
        name="localface",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=f"failed C:\\Users\\person\\private.jpg token={token}",
        args=(),
        exc_info=None,
    )
    record.safe_fields = {
        "route": "/jobs/{job_id}",
        "status_code": 500,
        "private_image": "raw bytes",
    }

    payload = json.loads(PrivacyJsonFormatter().format(record))

    assert payload["event"] == "failed [REDACTED_PATH] token=[REDACTED]"
    assert payload["route"] == "/jobs/{job_id}"
    assert payload["status_code"] == 500
    assert "private_image" not in payload
