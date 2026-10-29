"""Health checks and launcher smoke tests must never use a person's runtime."""

import argparse
import socket
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI

from localface_studio.api.app import create_app
from localface_studio.infrastructure.config import Settings
from scripts import run_dev, verify_backend, verify_frontend


def test_backend_smoke_ignores_user_runtime_and_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = tmp_path / "private-runtime"
    private.mkdir()
    sentinel = private / "do-not-touch.txt"
    sentinel.write_text("private data", encoding="utf-8")
    monkeypatch.setenv("LOCALFACE_RUNTIME_DIRECTORY", str(private))
    monkeypatch.setenv("LOCALFACE_WORKFLOW_BACKEND", "comfyui")
    monkeypatch.setattr(verify_backend, "ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "LOCALFACE_COMFYUI_URL=https://invalid.example\n",
        encoding="utf-8",
    )
    seen: list[Settings] = []

    def recorded(settings: Settings) -> FastAPI:
        seen.append(settings)
        return create_app(settings)

    monkeypatch.setattr(verify_backend, "create_app", recorded)
    verify_backend.main()

    assert len(seen) == 1
    assert seen[0].workflow_backend == "simulation"
    assert seen[0].runtime_directory.parent == tmp_path / ".tools"
    assert not seen[0].runtime_directory.exists()
    assert list(private.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8") == "private data"


def test_frontend_smoke_allocates_temporary_runtime_and_reserves_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verify_frontend, "ROOT", tmp_path)
    monkeypatch.setattr(
        verify_frontend,
        "parse_args",
        lambda: argparse.Namespace(backend_port=0),
    )
    directories: list[Path] = []

    def recorded(args: argparse.Namespace, runtime: Path, listener: socket.socket) -> None:
        assert args.backend_port == 0
        assert listener.getsockname()[1] > 0
        assert runtime.is_dir()
        assert runtime.parent == tmp_path / ".tools"
        directories.append(runtime)

    monkeypatch.setattr(verify_frontend, "verify", recorded)
    verify_frontend.main()
    assert len(directories) == 1
    assert not directories[0].exists()


@pytest.mark.parametrize("smoke_test", [True, False])
def test_launcher_isolation_only_applies_to_smoke_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    smoke_test: bool,
) -> None:
    monkeypatch.setattr(run_dev, "ROOT", tmp_path)
    monkeypatch.setattr(run_dev, "parse_args", lambda: argparse.Namespace(smoke_test=smoke_test))
    directories: list[Path | None] = []

    def recorded(args: argparse.Namespace, *, smoke_runtime: Path | None = None) -> None:
        assert args.smoke_test is smoke_test
        if smoke_test:
            assert smoke_runtime is not None and smoke_runtime.is_dir()
        directories.append(smoke_runtime)

    monkeypatch.setattr(run_dev, "run_services", recorded)
    run_dev.main()
    assert len(directories) == 1
    if smoke_test:
        assert directories[0] is not None and not directories[0].exists()
    else:
        assert directories == [None]


def test_launcher_smoke_forces_isolated_child_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for relative in (
        ".venv/Scripts/python.exe",
        "frontend/node_modules/vite/bin/vite.js",
        "frontend/dist/index.html",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(run_dev, "ROOT", tmp_path)
    monkeypatch.setattr(run_dev, "resolve_node", lambda: "node")
    monkeypatch.setenv("LOCALFACE_RUNTIME_DIRECTORY", str(tmp_path / "private"))
    monkeypatch.setenv("LOCALFACE_WORKFLOW_BACKEND", "native-research")
    environments: list[dict[str, str]] = []

    class Process:
        pass

    def spawn(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        creationflags: int,
    ) -> Process:
        environments.append(env.copy())
        return Process()

    stopped: list[Process] = []
    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(run_dev, "wait_until_ready", lambda *_: None)
    monkeypatch.setattr(run_dev, "stop_process", stopped.append)
    runtime = tmp_path / "isolated"
    run_dev.run_services(
        argparse.Namespace(backend_port=18001, frontend_port=15174, smoke_test=True),
        smoke_runtime=runtime,
    )
    assert len(environments) == 2
    assert len(stopped) == 2
    for environment in environments:
        assert environment["LOCALFACE_RUNTIME_DIRECTORY"] == str(runtime)
        assert environment["LOCALFACE_WORKFLOW_BACKEND"] == "simulation"
