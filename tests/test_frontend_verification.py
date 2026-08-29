import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scripts import verify_frontend


def test_screenshot_uses_disposable_edge_profile(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    profiles: list[Path] = []
    original_is_file = Path.is_file

    def fake_is_file(path: Path) -> bool:
        return path.name == "msedge.exe" or original_is_file(path)

    def fake_run(arguments: list[str], **_: object) -> SimpleNamespace:
        profile_argument = next(
            value for value in arguments if value.startswith("--user-data-dir=")
        )
        screenshot_argument = next(
            value for value in arguments if value.startswith("--screenshot=")
        )
        profile = Path(profile_argument.split("=", 1)[1])
        assert profile.is_dir()
        profiles.append(profile)
        Path(screenshot_argument.split("=", 1)[1]).write_bytes(b"png")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(verify_frontend, "ROOT", tmp_path)
    monkeypatch.setattr(Path, "is_file", fake_is_file)
    monkeypatch.setattr(subprocess, "run", fake_run)

    output = verify_frontend.capture_screenshot(
        tmp_path / "screenshots" / "page.png",
        "http://127.0.0.1:18021/",
    )

    assert output.read_bytes() == b"png"
    assert len(profiles) == 1
    assert profiles[0].name.startswith("edge-profile-")
    assert not profiles[0].exists()
