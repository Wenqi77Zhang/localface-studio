"""Face detection API tests using generated geometry and a fake detector."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from localface_studio.api.app import create_app
from localface_studio.api.security import CSRF_HEADER
from localface_studio.domain.faces import (
    DetectedFace,
    FaceBox,
    FacePoint,
    stable_detection_id,
)
from localface_studio.infrastructure.config import Settings

LOCAL_ORIGIN = "http://127.0.0.1:5173"
DETECTOR_ID = "yunet-opencv"
SCRFD_RESEARCH_MODEL_ID = "scrfd-insightface-research"


class FakeDetector:
    def __init__(self, face_count: int, detector_id: str = DETECTOR_ID) -> None:
        self._face_count = face_count
        self._detector_id = detector_id
        self.seen_bgr: np.ndarray | None = None

    @property
    def detector_id(self) -> str:
        return self._detector_id

    def detect(self, image: np.ndarray) -> tuple[DetectedFace, ...]:
        self.seen_bgr = image.copy()
        return tuple(_face(index * 30 + 5, self._detector_id) for index in range(self._face_count))


@asynccontextmanager
async def running_client(app) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
        ) as client:
            yield client


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 30), color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def exif_rotated_jpeg_bytes() -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", (40, 30), color=(10, 20, 30))
    image.getexif()[274] = 6
    image.save(buffer, format="JPEG", exif=image.getexif(), quality=100, subsampling=0)
    return buffer.getvalue()


async def establish_session(client: httpx.AsyncClient) -> str:
    response = await client.get("/api/v1/session")
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def test_single_face_is_auto_selected_and_pixels_are_deleted(tmp_path: Path) -> None:
    async def scenario() -> None:
        detector = FakeDetector(1)
        app = create_app(
            Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"),
            face_detectors={DETECTOR_ID: detector},
        )
        async with running_client(app) as client:
            csrf = await establish_session(client)
            response = await client.post(
                "/api/v1/face-detections",
                data={"role": "source", "detector_id": DETECTOR_ID},
                files={"image": ("private.png", png_bytes(), "image/png")},
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )

        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        payload = response.json()
        assert payload["role"] == "source"
        assert payload["detector_id"] == DETECTOR_ID
        assert payload["width"] == 40
        assert payload["height"] == 30
        assert len(payload["faces"]) == 1
        assert payload["selected_detection_id"] == payload["faces"][0]["detection_id"]
        assert payload["selection_required"] is False
        assert "actor" not in response.text
        assert "sha256" not in response.text
        assert "private.png" not in response.text
        assert list((tmp_path / "runtime" / "tasks").iterdir()) == []
        assert detector.seen_bgr is not None
        assert detector.seen_bgr[0, 0].tolist() == [30, 20, 10]

    asyncio.run(scenario())


def test_exif_orientation_controls_detector_pixels_and_response_geometry(tmp_path: Path) -> None:
    async def scenario() -> None:
        detector = FakeDetector(1)
        app = create_app(
            Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"),
            face_detectors={DETECTOR_ID: detector},
        )
        async with running_client(app) as client:
            csrf = await establish_session(client)
            response = await client.post(
                "/api/v1/face-detections",
                data={"role": "source", "detector_id": DETECTOR_ID},
                files={"image": ("oriented.jpg", exif_rotated_jpeg_bytes(), "image/jpeg")},
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )

        assert response.status_code == 201
        assert response.json()["width"] == 30
        assert response.json()["height"] == 40
        assert detector.seen_bgr is not None
        assert detector.seen_bgr.shape == (40, 30, 3)

    asyncio.run(scenario())


def test_multi_face_selection_is_actor_isolated_and_revision_specific(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        app = create_app(
            Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"),
            face_detectors={DETECTOR_ID: FakeDetector(2)},
        )
        async with running_client(app) as owner:
            csrf = await establish_session(owner)
            created = await owner.post(
                "/api/v1/face-detections",
                data={"role": "target"},
                files={"image": ("target.png", png_bytes(), "image/png")},
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            payload = created.json()
            invalid = await owner.post(
                f"/api/v1/face-detections/{payload['revision_id']}/selection",
                json={"detection_id": "face_00000000000000000000"},
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            selected = await owner.post(
                f"/api/v1/face-detections/{payload['revision_id']}/selection",
                json={"detection_id": payload["faces"][1]["detection_id"]},
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf},
            )
            readable = await owner.get(f"/api/v1/face-detections/{payload['revision_id']}")

        async with running_client(app) as stranger:
            stranger_csrf = await establish_session(stranger)
            hidden_read = await stranger.get(f"/api/v1/face-detections/{payload['revision_id']}")
            hidden_write = await stranger.post(
                f"/api/v1/face-detections/{payload['revision_id']}/selection",
                json={"detection_id": payload["faces"][0]["detection_id"]},
                headers={"Origin": LOCAL_ORIGIN, CSRF_HEADER: stranger_csrf},
            )

        assert created.status_code == 201
        assert payload["selected_detection_id"] is None
        assert payload["selection_required"] is True
        assert invalid.status_code == 409
        assert invalid.json()["code"] == "face_selection_invalid"
        assert selected.status_code == 200
        assert selected.json()["selected_detection_id"] == payload["faces"][1]["detection_id"]
        assert readable.json() == selected.json()
        assert hidden_read.status_code == 404
        assert hidden_write.status_code == 404

    asyncio.run(scenario())


def test_new_upload_invalidates_old_revision_and_no_face_is_explicit(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        app = create_app(
            Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"),
            face_detectors={DETECTOR_ID: FakeDetector(0)},
        )
        async with running_client(app) as client:
            csrf = await establish_session(client)
            headers = {"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf}
            first = await client.post(
                "/api/v1/face-detections",
                data={"role": "source"},
                files={"image": ("first.png", png_bytes(), "image/png")},
                headers=headers,
            )
            second = await client.post(
                "/api/v1/face-detections",
                data={"role": "source"},
                files={"image": ("second.png", png_bytes(), "image/png")},
                headers=headers,
            )
            stale = await client.get(f"/api/v1/face-detections/{first.json()['revision_id']}")

        assert second.status_code == 201
        assert second.json()["faces"] == []
        assert second.json()["selected_detection_id"] is None
        assert second.json()["selection_required"] is False
        assert stale.status_code == 404

    asyncio.run(scenario())


def test_scrfd_requires_explicit_research_acceptance_before_upload(tmp_path: Path) -> None:
    async def scenario() -> None:
        detector = FakeDetector(1, SCRFD_RESEARCH_MODEL_ID)
        app = create_app(
            Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"),
            face_detectors={SCRFD_RESEARCH_MODEL_ID: detector},
        )
        async with running_client(app) as client:
            csrf = await establish_session(client)
            headers = {"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf}
            missing = await client.post(
                "/api/v1/face-detections",
                data={"role": "source", "detector_id": SCRFD_RESEARCH_MODEL_ID},
                files={"image": ("private.png", png_bytes(), "image/png")},
                headers=headers,
            )
            rejected = await client.post(
                "/api/v1/face-detections",
                data={
                    "role": "source",
                    "detector_id": SCRFD_RESEARCH_MODEL_ID,
                    "research_license_accepted": "false",
                },
                files={"image": ("private.png", png_bytes(), "image/png")},
                headers=headers,
            )

        assert missing.status_code == 403
        assert missing.json()["code"] == "research_model_license_not_accepted"
        assert rejected.status_code == 403
        assert rejected.json()["code"] == "research_model_license_not_accepted"
        assert detector.seen_bgr is None
        assert list((tmp_path / "runtime" / "tasks").iterdir()) == []

    asyncio.run(scenario())


def test_scrfd_acceptance_is_strict_and_allows_an_explicit_true(tmp_path: Path) -> None:
    async def scenario() -> None:
        detector = FakeDetector(1, SCRFD_RESEARCH_MODEL_ID)
        app = create_app(
            Settings(log_level="CRITICAL", runtime_directory=tmp_path / "runtime"),
            face_detectors={SCRFD_RESEARCH_MODEL_ID: detector},
        )
        async with running_client(app) as client:
            csrf = await establish_session(client)
            headers = {"Origin": LOCAL_ORIGIN, CSRF_HEADER: csrf}
            invalid = await client.post(
                "/api/v1/face-detections",
                data={
                    "role": "source",
                    "detector_id": SCRFD_RESEARCH_MODEL_ID,
                    "research_license_accepted": "yes",
                },
                files={"image": ("private.png", png_bytes(), "image/png")},
                headers=headers,
            )
            accepted = await client.post(
                "/api/v1/face-detections",
                data={
                    "role": "source",
                    "detector_id": SCRFD_RESEARCH_MODEL_ID,
                    "research_license_accepted": "true",
                },
                files={"image": ("private.png", png_bytes(), "image/png")},
                headers=headers,
            )

        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_detection_form"
        assert accepted.status_code == 201
        assert accepted.json()["detector_id"] == SCRFD_RESEARCH_MODEL_ID
        assert detector.seen_bgr is not None
        assert list((tmp_path / "runtime" / "tasks").iterdir()) == []

    asyncio.run(scenario())


def _face(x: float, detector_id: str = DETECTOR_ID) -> DetectedFace:
    box = FaceBox(x=x, y=4, width=20, height=20)
    landmarks = tuple(FacePoint(x=x + index + 1, y=8 + index) for index in range(5))
    return DetectedFace(
        detection_id=stable_detection_id(detector_id, box, landmarks),
        detector_id=detector_id,
        box=box,
        landmarks=landmarks,
        confidence=0.96,
    )
