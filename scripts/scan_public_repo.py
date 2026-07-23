"""Reject sensitive text, prohibited assets, and oversized tracked files."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_SIZE = 2 * 1024 * 1024
FORBIDDEN_SUFFIXES = {
    ".bin",
    ".ckpt",
    ".engine",
    ".onnx",
    ".pdf",
    ".pt",
    ".pth",
    ".safetensors",
}
TEXT_SUFFIXES = {
    "",
    ".css",
    ".example",
    ".html",
    ".json",
    ".lock",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SENSITIVE_PATTERNS = {
    "Windows user path": re.compile(r"(?i)\b[A-Z]:\\Users\\"),
    "private key header": re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]+\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}


def main() -> None:
    """Scan files already tracked or staged for the public repository."""
    failures: list[str] = []
    for relative_path in tracked_files():
        path = ROOT / relative_path
        if not path.is_file():
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"{relative_path}: prohibited asset type")
            continue
        if path.stat().st_size > MAX_FILE_SIZE:
            failures.append(f"{relative_path}: exceeds {MAX_FILE_SIZE} bytes")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{relative_path}: matched {label}")

    if failures:
        raise SystemExit("Public repository scan failed:\n" + "\n".join(sorted(failures)))
    print("Public repository scan: OK")


def tracked_files() -> list[Path]:
    """Return public candidates without inspecting ignored private data."""
    completed = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [Path(item.decode("utf-8")) for item in completed.stdout.split(b"\0") if item]


if __name__ == "__main__":
    main()
