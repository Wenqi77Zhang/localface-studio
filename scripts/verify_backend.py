"""Start the local API briefly and verify its privacy-safe health endpoint."""

from __future__ import annotations

import json
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

HOST = "127.0.0.1"
PORT = 8765
HEALTH_URL = f"http://{HOST}:{PORT}/api/v1/health"


def main() -> None:
    """Run a bounded local smoke test without leaving a server process behind."""
    config = uvicorn.Config(
        "localface_studio.main:app",
        host=HOST,
        port=PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        payload = wait_for_health()
        if payload != {"status": "ok"}:
            raise RuntimeError(f"Unexpected health response: {payload!r}")
        print(json.dumps(payload, separators=(",", ":")))
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    if thread.is_alive():
        raise RuntimeError("The verification server did not stop cleanly.")


def wait_for_health() -> dict[str, str]:
    """Poll the loopback-only endpoint for at most five seconds."""
    deadline = time.monotonic() + 5
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with urlopen(HEALTH_URL, timeout=1) as response:
                payload: object = json.load(response)
                if payload != {"status": "ok"}:
                    raise RuntimeError(f"Unexpected health response: {payload!r}")
                return {"status": "ok"}
        except (URLError, TimeoutError) as error:
            last_error = error
            time.sleep(0.1)

    raise RuntimeError("The health endpoint did not become ready.") from last_error


if __name__ == "__main__":
    main()
