"""Versioned, implementation-free ports reserved for a future video pipeline."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from localface_studio.domain.faces import DetectedFace

VIDEO_CONTRACT_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class VideoFrame:
    """One decoded BGR frame with deterministic timeline coordinates."""

    index: int
    timestamp_seconds: float
    pixels: NDArray[np.uint8]

    def __post_init__(self) -> None:
        if self.index < 0 or self.timestamp_seconds < 0:
            raise ValueError("video frame coordinates must not be negative")
        if self.pixels.dtype != np.uint8 or self.pixels.ndim != 3 or self.pixels.shape[2] != 3:
            raise ValueError("video frame must be an HxWx3 uint8 BGR array")


@dataclass(frozen=True, slots=True)
class TrackedFace:
    """Task-local face continuity without a persisted identity embedding."""

    track_id: str
    detection: DetectedFace
    first_frame_index: int
    last_frame_index: int

    def __post_init__(self) -> None:
        if not self.track_id.strip() or self.first_frame_index < 0:
            raise ValueError("video face track is invalid")
        if self.last_frame_index < self.first_frame_index:
            raise ValueError("video face track frame range is invalid")


@dataclass(frozen=True, slots=True)
class VideoCheckpoint:
    """Non-biometric restart marker; identity vectors are deliberately absent."""

    task_id: str
    source_digest: str
    next_frame_index: int
    completed_fragment_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id.strip() or len(self.source_digest) != 64:
            raise ValueError("video checkpoint identity is invalid")
        if self.next_frame_index < 0 or any(
            not item.strip() for item in self.completed_fragment_ids
        ):
            raise ValueError("video checkpoint progress is invalid")


class FrameSource(Protocol):
    """Decode frames in timestamp order without exposing container internals."""

    def frames(self) -> AsyncIterator[VideoFrame]: ...


class FaceTracker(Protocol):
    """Associate detections with task-local tracks across adjacent frames."""

    async def update(
        self,
        frame: VideoFrame,
        detections: tuple[DetectedFace, ...],
    ) -> tuple[TrackedFace, ...]: ...


class TemporalConsistencyProcessor(Protocol):
    """Stabilize one swapped frame without changing its timeline coordinate."""

    async def apply(
        self,
        frame: VideoFrame,
        selected_track: TrackedFace,
        previous_result: VideoFrame | None,
    ) -> VideoFrame: ...


class AudioMuxer(Protocol):
    """Copy authorized source audio into a completed silent video artifact."""

    async def mux(self, silent_video: Path, source_media: Path, destination: Path) -> None: ...


class VideoCheckpointStore(Protocol):
    """Persist restart progress while excluding frames and biometric representations."""

    def load(self, task_id: str) -> VideoCheckpoint | None: ...

    def save(self, checkpoint: VideoCheckpoint) -> None: ...

    def remove(self, task_id: str) -> None: ...


VideoProgressReporter = Callable[[int, int | None], Awaitable[None]]


class VideoWorkflowBackend(Protocol):
    """Future video boundary kept separate from the frozen image task contract."""

    async def run_video(
        self,
        task_id: str,
        frame_source: FrameSource,
        report_progress: VideoProgressReporter,
    ) -> None: ...
