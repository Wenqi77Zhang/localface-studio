"""Start the local API briefly and verify its privacy-safe health endpoint."""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from localface_studio.api.app import create_app
from localface_studio.infrastructure.config import VerificationSettings

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"


def main() -> None:
    """Never import the user's configured app or touch its retained workspaces."""
    parent = ROOT / ".tools"
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="backend-smoke-", dir=parent) as directory:
        verify(Path(directory))


def verify(runtime_directory: Path) -> None:
    """Reserve an ephemeral port so a different running service cannot pass this test."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((HOST, 0))
        port = listener.getsockname()[1]
        verify_server(runtime_directory, listener, port)


def verify_server(runtime_directory: Path, listener: socket.socket, port: int) -> None:
    """Run a bounded health smoke test with an explicitly isolated simulation app."""
    application = create_app(
        VerificationSettings(
            host=HOST,
            port=port,
            runtime_directory=runtime_directory,
            workflow_backend="simulation",
        )
    )
    config = uvicorn.Config(
        application,
        host=HOST,
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()

    try:
        payload = wait_for_health(f"http://{HOST}:{port}/api/v1/health")
        if payload != {"status": "ok"}:
            raise RuntimeError(f"Unexpected health response: {payload!r}")
        print(json.dumps(payload, separators=(",", ":")))
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    if thread.is_alive():
        raise RuntimeError("The verification server did not stop cleanly.")


def wait_for_health(url: str) -> dict[str, str]:
    """Poll the loopback-only endpoint for at most five seconds."""
    deadline = time.monotonic() + 5
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
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
