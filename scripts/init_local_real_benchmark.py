"""Initialize the ignored real-image benchmark workspace."""

from pathlib import Path

from localface_studio.benchmarking.local_real_images import initialize_local_workspace

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "runtime"
WORKSPACE = PRIVATE_ROOT / "benchmarks" / "real"


def main() -> None:
    created = initialize_local_workspace(WORKSPACE, allowed_root=PRIVATE_ROOT)
    if created:
        print("Created local-only benchmark files:")
        for path in created:
            print(f"- {path.relative_to(ROOT)}")
    else:
        print("Local-only benchmark workspace already exists; nothing was overwritten.")
    print("Private workspace: runtime/benchmarks/real/")


if __name__ == "__main__":
    main()
