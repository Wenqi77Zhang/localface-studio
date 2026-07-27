"""Ephemeral, actor-isolated face detection revisions."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Lock
from uuid import uuid4

import numpy as np
from PIL import Image

from localface_studio.application.face_detection import FaceDetector
from localface_studio.application.uploads import AsyncUpload, TaskUploadService
from localface_studio.domain.faces import DetectedFace
from localface_studio.domain.images import ImageRole

DETECTION_REVISION_TTL = timedelta(minutes=30)
MAXIMUM_DETECTION_REVISIONS = 256


class DetectionRevisionError(RuntimeError):
    """Expected detection workflow failure with a stable public error code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True, slots=True)
class DetectionRevision:
    """Privacy-safe detector output tied to one image content revision."""

    revision_id: str
    actor_id: str
    role: ImageRole
    detector_id: str
    content_sha256: str
    width: int
    height: int
    faces: tuple[DetectedFace, ...]
    selected_detection_id: str | None
    created_at: datetime
    expires_at: datetime

    @property
    def selection_required(self) -> bool:
        return len(self.faces) > 1 and self.selected_detection_id is None


class DetectionRevisionStore:
    """Bounded process-local store that exposes records only to their actor."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        ttl: timedelta = DETECTION_REVISION_TTL,
        maximum_records: int = MAXIMUM_DETECTION_REVISIONS,
    ) -> None:
        if ttl <= timedelta(0) or maximum_records < 1:
            raise ValueError("detection revision bounds must be positive")
        self._clock = clock or _utc_now
        self._ttl = ttl
        self._maximum_records = maximum_records
        self._records: dict[str, DetectionRevision] = {}
        self._active_by_role: dict[tuple[str, ImageRole], str] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        actor_id: str,
        role: ImageRole,
        detector_id: str,
        content_sha256: str,
        width: int,
        height: int,
        faces: tuple[DetectedFace, ...],
    ) -> DetectionRevision:
        now = self._aware_now()
        selected = faces[0].detection_id if len(faces) == 1 else None
        record = DetectionRevision(
            revision_id=uuid4().hex,
            actor_id=actor_id,
            role=role,
            detector_id=detector_id,
            content_sha256=content_sha256,
            width=width,
            height=height,
            faces=faces,
            selected_detection_id=selected,
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._prune(now)
            previous_id = self._active_by_role.get((actor_id, role))
            if previous_id is not None:
                self._records.pop(previous_id, None)
            self._records[record.revision_id] = record
            self._active_by_role[(actor_id, role)] = record.revision_id
            self._trim()
        return record

    def get_for_actor(self, revision_id: str, actor_id: str) -> DetectionRevision | None:
        now = self._aware_now()
        with self._lock:
            self._prune(now)
            record = self._records.get(revision_id)
            if record is None or record.actor_id != actor_id:
                return None
            return record

    def invalidate(self, actor_id: str, role: ImageRole) -> None:
        """Forget the previous upload revision before replacement processing begins."""
        with self._lock:
            revision_id = self._active_by_role.get((actor_id, role))
            if revision_id is not None:
                self._remove(revision_id)

    def select(
        self,
        revision_id: str,
        actor_id: str,
        detection_id: str,
    ) -> DetectionRevision | None:
        now = self._aware_now()
        with self._lock:
            self._prune(now)
            record = self._records.get(revision_id)
            if record is None or record.actor_id != actor_id:
                return None
            if detection_id not in {face.detection_id for face in record.faces}:
                raise DetectionRevisionError(
                    "face_selection_invalid",
                    "The selected face does not belong to this detection revision.",
                )
            updated = replace(record, selected_detection_id=detection_id)
            self._records[revision_id] = updated
            return updated

    def _prune(self, now: datetime) -> None:
        expired = [
            revision_id for revision_id, record in self._records.items() if record.expires_at <= now
        ]
        for revision_id in expired:
            self._remove(revision_id)

    def _trim(self) -> None:
        excess = len(self._records) - self._maximum_records
        if excess <= 0:
            return
        oldest = sorted(self._records.values(), key=lambda record: record.created_at)[:excess]
        for record in oldest:
            self._remove(record.revision_id)

    def _remove(self, revision_id: str) -> None:
        record = self._records.pop(revision_id, None)
        if record is None:
            return
        key = (record.actor_id, record.role)
        if self._active_by_role.get(key) == revision_id:
            self._active_by_role.pop(key, None)

    def _aware_now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("detection revision clock must be timezone-aware")
        return now


class FaceDetectionService:
    """Detect one upload and delete its temporary pixels in all outcomes."""

    def __init__(
        self,
        upload_service: TaskUploadService,
        input_path: Callable[[str, ImageRole], Path],
        detector_resolver: Callable[[str], FaceDetector],
        revisions: DetectionRevisionStore,
    ) -> None:
        self._uploads = upload_service
        self._input_path = input_path
        self._detector_resolver = detector_resolver
        self._revisions = revisions

    async def detect(
        self,
        *,
        actor_id: str,
        role: ImageRole,
        detector_id: str,
        upload: AsyncUpload,
    ) -> DetectionRevision:
        workspace_id = uuid4().hex
        self._revisions.invalidate(actor_id, role)
        try:
            validated = await self._uploads.save_single(workspace_id, role, upload)
            path = self._input_path(workspace_id, role)
            content_sha256 = await asyncio.to_thread(_file_sha256, path)
            image = await asyncio.to_thread(_decode_bgr, path)
            try:
                detector = self._detector_resolver(detector_id)
                faces = await asyncio.to_thread(detector.detect, image)
            except DetectionRevisionError:
                raise
            except Exception as error:
                raise DetectionRevisionError(
                    "face_detector_unavailable",
                    "The selected face detector is unavailable.",
                ) from error
            if detector.detector_id != detector_id:
                raise DetectionRevisionError(
                    "face_detector_mismatch",
                    "The selected face detector returned an unexpected identity.",
                )
            return self._revisions.create(
                actor_id=actor_id,
                role=role,
                detector_id=detector.detector_id,
                content_sha256=content_sha256,
                width=validated.width,
                height=validated.height,
                faces=faces,
            )
        finally:
            self._uploads.discard(workspace_id)


class CachedDetectorResolver:
    """Lazily create and cache configured detector adapters."""

    def __init__(self, factories: dict[str, Callable[[], FaceDetector]]) -> None:
        self._factories = dict(factories)
        self._instances: dict[str, FaceDetector] = {}
        self._lock = Lock()

    def __call__(self, detector_id: str) -> FaceDetector:
        with self._lock:
            existing = self._instances.get(detector_id)
            if existing is not None:
                return existing
            factory = self._factories.get(detector_id)
            if factory is None:
                raise DetectionRevisionError(
                    "face_detector_unknown",
                    "The selected face detector is not configured.",
                )
            detector = factory()
            if detector.detector_id != detector_id:
                raise DetectionRevisionError(
                    "face_detector_mismatch",
                    "The configured face detector identity does not match.",
                )
            self._instances[detector_id] = detector
            return detector


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_bgr(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def _utc_now() -> datetime:
    return datetime.now(UTC)
