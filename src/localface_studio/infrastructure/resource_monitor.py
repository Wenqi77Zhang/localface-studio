"""Sample local process RSS and device VRAM without recording hardware identifiers."""

import os
import subprocess
from threading import Event, Thread
from time import monotonic
from types import TracebackType

import psutil


def device_vram_mb() -> float | None:
    """Total used VRAM across devices, NOT this process's CUDA allocation peak."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        values = [float(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        return sum(values) if values else None
    except OSError, ValueError, subprocess.SubprocessError:
        return None


class ResourceMonitor:
    """Bounded sampler; missing GPU telemetry stays null, never becomes a fake zero."""

    def __init__(self, *, interval: float = 0.1, sample_gpu: bool = True) -> None:
        if interval <= 0:
            raise ValueError("sampling interval must be positive")
        self._interval = interval
        self._sample_gpu = sample_gpu
        self._process = psutil.Process()
        self._stop = Event()
        self._thread: Thread | None = None
        self._started = 0.0
        self._rss_start = 0.0
        self._rss_peak = 0.0
        self._vram_peak: float | None = None
        self._gpu_sampled_at = -2.0
        self._samples = 0
        self.metrics: dict[str, float | int | None] = {}

    def __enter__(self) -> ResourceMonitor:
        self._started = monotonic()
        self._rss_start = self._process.memory_info().rss / (1024 * 1024)
        self._rss_peak = self._rss_start
        self._thread = Thread(target=self._sample, name="localface-resource-sampler", daemon=True)
        self._thread.start()
        return self

    def _sample(self) -> None:
        while not self._stop.is_set():
            rss = self._process.memory_info().rss / (1024 * 1024)
            self._rss_peak = max(self._rss_peak, rss)
            self._samples += 1
            now = monotonic()
            if self._sample_gpu and now - self._gpu_sampled_at >= 1:
                used = device_vram_mb()
                if used is not None:
                    self._vram_peak = max(self._vram_peak or 0.0, used)
                self._gpu_sampled_at = now
            self._stop.wait(self._interval)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        duration = monotonic() - self._started
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        rss_end = self._process.memory_info().rss / (1024 * 1024)
        self.metrics = {
            "duration_ms": round(duration * 1000, 2),
            "rss_start_mb": round(self._rss_start, 2),
            "rss_end_mb": round(rss_end, 2),
            "rss_peak_mb": round(max(self._rss_peak, rss_end), 2),
            "device_vram_peak_mb": self._vram_peak,
            "resource_samples": self._samples,
        }
