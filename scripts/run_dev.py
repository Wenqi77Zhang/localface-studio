"""Run the loopback-only backend and frontend as one managed process group."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
BACKEND_URL = f"http://{HOST}:8000/api/v1/health"
FRONTEND_URL = f"http://{HOST}:5173/"


def main() -> None:
    """Start both services, optionally open a browser, and clean up on exit."""
    args = parse_args()
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    node = ROOT / ".tools" / "node" / "node.exe"
    vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    for required in (python, node, vite):
        if not required.is_file():
            raise RuntimeError(f"Required local tool is missing: {required.relative_to(ROOT)}")

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    environment = clean_windows_environment()
    backend = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "localface_studio.main:app",
            "--host",
            HOST,
            "--port",
            "8000",
        ],
        cwd=ROOT,
        env=environment,
        creationflags=creation_flags,
    )
    frontend = subprocess.Popen(
        [str(node), str(vite), "--host", HOST, "--port", "5173", "--strictPort"],
        cwd=ROOT / "frontend",
        env=environment,
        creationflags=creation_flags,
    )

    try:
        wait_until_ready(BACKEND_URL, backend, frontend)
        wait_until_ready(FRONTEND_URL, backend, frontend)
        print(f"LocalFace Studio is ready: {FRONTEND_URL}")
        if args.smoke_test:
            return
        if not args.no_browser:
            webbrowser.open(FRONTEND_URL)
        print("Press Ctrl+C to stop both services.")
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(0.25)
        raise RuntimeError("A LocalFace Studio service stopped unexpectedly.")
    except KeyboardInterrupt:
        print("Stopping LocalFace Studio...")
    finally:
        stop_process(frontend)
        stop_process(backend)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
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


def wait_until_ready(
    url: str,
    backend: subprocess.Popen[bytes],
    frontend: subprocess.Popen[bytes],
) -> None:
    """Wait up to fifteen seconds while ensuring neither service exits."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if backend.poll() is not None or frontend.poll() is not None:
            raise RuntimeError("A service exited before startup completed.")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except URLError, TimeoutError:
            time.sleep(0.1)
    raise RuntimeError(f"Local service did not become ready: {url}")


def stop_process(process: subprocess.Popen[bytes]) -> None:
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
