"""Resource measurements must remain bounded, numeric and explicitly nullable."""

import subprocess
import time

import pytest

from localface_studio.infrastructure import resource_monitor as resources


def test_gpu_sample_unavailable_is_not_fabricated_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", unavailable)
    assert resources.device_vram_mb() is None
    with resources.ResourceMonitor(interval=0.005) as monitor:
        time.sleep(0.025)
    assert monitor.metrics["device_vram_peak_mb"] is None
    assert float(str(monitor.metrics["rss_peak_mb"])) > 0
    assert float(str(monitor.metrics["duration_ms"])) > 0
    assert int(str(monitor.metrics["resource_samples"])) >= 1


def test_device_vram_sums_only_numeric_device_measurements(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, stdout="128\n256\n"),
    )
    assert resources.device_vram_mb() == 384
    with pytest.raises(ValueError, match="positive"):
        resources.ResourceMonitor(interval=0)
