"""Reject prohibited binary assets and oversized blobs anywhere in Git history."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_BLOB_SIZE = 2 * 1024 * 1024
FORBIDDEN_SUFFIXES = {
    ".7z",
    ".bin",
    ".bmp",
    ".ckpt",
    ".engine",
    ".gif",
    ".jpeg",
    ".jpg",
    ".onnx",
    ".pdf",
    ".png",
    ".pt",
    ".pth",
    ".rar",
    ".safetensors",
    ".webp",
    ".zip",
}
AUDITED_SYNTHETIC_PREFIX = "benchmarks/face_detection/public/assets/"


def main() -> None:
    """Inspect all reachable historical objects without checking out old revisions."""
    objects = _git("rev-list", "--objects", "--all").splitlines()
    paths: dict[str, set[str]] = {}
    for line in objects:
        object_id, separator, path = line.partition(" ")
        if separator and path:
            paths.setdefault(object_id, set()).add(path)

    batch_input = "".join(f"{object_id}\n" for object_id in paths)
    completed = subprocess.run(
        ["git", "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        cwd=ROOT,
        input=batch_input,
        text=True,
        capture_output=True,
        check=True,
    )
    failures: set[str] = set()
    for line in completed.stdout.splitlines():
        object_id, object_type, raw_size = line.split()
        if object_type != "blob":
            continue
        size = int(raw_size)
        for path in paths.get(object_id, set()):
            suffix = PurePosixPath(path).suffix.casefold()
            if suffix in FORBIDDEN_SUFFIXES and not path.startswith(AUDITED_SYNTHETIC_PREFIX):
                failures.add(f"{path}: prohibited historical asset type")
            if size > MAX_BLOB_SIZE:
                failures.add(f"{path}: historical blob exceeds {MAX_BLOB_SIZE} bytes")
    if failures:
        raise SystemExit("Git history scan failed:\n" + "\n".join(sorted(failures)))
    print("Git history asset scan: OK")


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout


if __name__ == "__main__":
    main()
