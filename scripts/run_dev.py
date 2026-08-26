"""Run the loopback-only backend and frontend as one managed process group."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"


def main() -> None:
    """Start both services, optionally open a browser, and clean up on exit."""
    args = parse_args()
    backend_url = f"http://{HOST}:{args.backend_port}/api/v1/health"
    frontend_url = f"http://{HOST}:{args.frontend_port}/"
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    node = resolve_node()
    vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    frontend_build = ROOT / "frontend" / "dist" / "index.html"
    for required in (python, vite, frontend_build):
        if not required.is_file():
            raise RuntimeError(f"Required local tool is missing: {required.relative_to(ROOT)}")

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    environment = clean_windows_environment()
    environment["LOCALFACE_API_TARGET"] = f"http://{HOST}:{args.backend_port}"
    environment["LOCALFACE_PORT"] = str(args.backend_port)
    environment["LOCALFACE_FRONTEND_PORT"] = str(args.frontend_port)
    backend = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "localface_studio.main:app",
            "--host",
            HOST,
            "--port",
            str(args.backend_port),
        ],
        cwd=ROOT,
        env=environment,
        creationflags=creation_flags,
    )
    frontend = subprocess.Popen(
        [
            node,
            str(vite),
            "preview",
            "--host",
            HOST,
            "--port",
            str(args.frontend_port),
            "--strictPort",
        ],
        cwd=ROOT / "frontend",
        env=environment,
        creationflags=creation_flags,
    )

    try:
        wait_until_ready(backend_url, backend, frontend)
        wait_until_ready(frontend_url, backend, frontend)
        print(f"LocalFace Studio is ready: {frontend_url}")
        if args.smoke_test:
            return
        if not args.no_browser:
            webbrowser.open(frontend_url)
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
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
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


def resolve_node() -> str:
    """Prefer the isolated runtime and allow the CI-provided Node.js fallback."""
    local_node = ROOT / ".tools" / "node" / "node.exe"
    if local_node.is_file():
        return str(local_node)
    system_node = shutil.which("node")
    if system_node is None:
        raise RuntimeError("Node.js is unavailable. Run setup.cmd first.")
    return system_node


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
