"""Verify the Vite frontend and its loopback proxy to the local API."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
FRONTEND_URL = f"http://{HOST}:{FRONTEND_PORT}/"
PROXIED_HEALTH_URL = f"http://{HOST}:{FRONTEND_PORT}/api/v1/health"


def main() -> None:
    """Run a bounded integration check and optionally capture a screenshot."""
    args = parse_args()
    node = ROOT / ".tools" / "node" / "node.exe"
    vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    if not node.is_file() or not vite.is_file():
        raise RuntimeError("Project-local Node.js or Vite is missing. Run npm install first.")

    backend = uvicorn.Server(
        uvicorn.Config(
            "localface_studio.main:app",
            host=HOST,
            port=BACKEND_PORT,
            log_level="warning",
        )
    )
    backend_thread = threading.Thread(target=backend.run, daemon=True)
    backend_thread.start()

    frontend = subprocess.Popen(
        [
            str(node),
            str(vite),
            "--host",
            HOST,
            "--port",
            str(FRONTEND_PORT),
            "--strictPort",
        ],
        cwd=ROOT / "frontend",
        env=clean_windows_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    try:
        html = wait_for_text(FRONTEND_URL)
        if "LocalFace Studio" not in html:
            raise RuntimeError("The frontend HTML does not contain the product title.")

        health = json.loads(wait_for_text(PROXIED_HEALTH_URL))
        if health != {"status": "ok"}:
            raise RuntimeError(f"Unexpected proxied health response: {health!r}")

        result: dict[str, object] = {
            "frontend": "ok",
            "api_proxy": "ok",
        }
        if args.screenshot:
            result["screenshot"] = str(capture_screenshot(args.screenshot))
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    finally:
        stop_process(frontend)
        backend.should_exit = True
        backend_thread.join(timeout=5)

    if backend_thread.is_alive():
        raise RuntimeError("The backend verification server did not stop cleanly.")


def parse_args() -> argparse.Namespace:
    """Parse the optional visual-verification output path."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    return parser.parse_args()


def clean_windows_environment() -> dict[str, str]:
    """Remove duplicate case-insensitive keys before creating Windows processes."""
    clean: dict[str, str] = {}
    seen: set[str] = set()
    for key, value in reversed(list(os.environ.items())):
        normalized = key.casefold()
        if normalized not in seen:
            clean[key] = value
            seen.add(normalized)
    return clean


def wait_for_text(url: str) -> str:
    """Read a fixed loopback URL, retrying for at most ten seconds."""
    deadline = time.monotonic() + 10
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                body: object = response.read()
                if not isinstance(body, bytes):
                    raise RuntimeError("Local service returned a non-byte response body.")
                return body.decode("utf-8")
        except (URLError, TimeoutError) as error:
            last_error = error
            time.sleep(0.1)
    raise RuntimeError(f"Local service did not become ready: {url}") from last_error


def capture_screenshot(output: Path) -> Path:
    """Capture the local page with Microsoft Edge in headless mode."""
    edge_candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    edge = next((candidate for candidate in edge_candidates if candidate.is_file()), None)
    if edge is None:
        raise RuntimeError("Microsoft Edge was not found for visual verification.")

    resolved_output = output.resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    profile = (ROOT / ".tools" / "edge-profile").resolve()
    profile.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            str(edge),
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--hide-scrollbars",
            "--window-size=1440,1000",
            f"--user-data-dir={profile}",
            f"--screenshot={resolved_output}",
            FRONTEND_URL,
        ],
        check=False,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0 or not resolved_output.is_file():
        raise RuntimeError("Microsoft Edge failed to capture the frontend screenshot.")
    return resolved_output


def stop_process(process: subprocess.Popen[str]) -> None:
    """Terminate a child process without leaving a local server behind."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


if __name__ == "__main__":
    main()
