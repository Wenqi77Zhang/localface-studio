"""Unit tests for bounded, actor-isolated detection revision state."""

from datetime import UTC, datetime, timedelta

import pytest

from localface_studio.application.detection_revisions import (
    DetectionRevisionError,
    DetectionRevisionStore,
)
from localface_studio.domain.faces import (
    DetectedFace,
    FaceBox,
    FacePoint,
    stable_detection_id,
)
from localface_studio.domain.images import ImageRole

DETECTOR_ID = "yunet-opencv"


def face(x: float) -> DetectedFace:
    box = FaceBox(x=x, y=10, width=20, height=24)
    landmarks = tuple(FacePoint(x=x + index + 1, y=12 + index) for index in range(5))
    return DetectedFace(
        detection_id=stable_detection_id(DETECTOR_ID, box, landmarks),
        detector_id=DETECTOR_ID,
        box=box,
        landmarks=landmarks,
        confidence=0.95,
    )


def test_single_face_auto_selects_and_new_same_role_invalidates_previous() -> None:
    store = DetectionRevisionStore()
    first = store.create(
        actor_id="actor-a",
        role=ImageRole.SOURCE,
        detector_id=DETECTOR_ID,
        content_sha256="a" * 64,
        width=100,
        height=80,
        faces=(face(10),),
    )
    second = store.create(
        actor_id="actor-a",
        role=ImageRole.SOURCE,
        detector_id=DETECTOR_ID,
        content_sha256="b" * 64,
        width=120,
        height=90,
        faces=(face(20),),
    )

    assert first.selected_detection_id == first.faces[0].detection_id
    assert first.selection_required is False
    assert store.get_for_actor(first.revision_id, "actor-a") is None
    assert store.get_for_actor(second.revision_id, "actor-a") == second
    assert store.get_for_actor(second.revision_id, "actor-b") is None


def test_multiple_faces_require_valid_explicit_selection() -> None:
    store = DetectionRevisionStore()
    revision = store.create(
        actor_id="actor-a",
        role=ImageRole.TARGET,
        detector_id=DETECTOR_ID,
        content_sha256="c" * 64,
        width=200,
        height=100,
        faces=(face(10), face(50)),
    )

    assert revision.selected_detection_id is None
    assert revision.selection_required is True
    with pytest.raises(DetectionRevisionError, match="does not belong") as caught:
        store.select(revision.revision_id, "actor-a", "face_00000000000000000000")
    assert caught.value.code == "face_selection_invalid"

    selected = store.select(revision.revision_id, "actor-a", revision.faces[1].detection_id)
    assert selected is not None
    assert selected.selected_detection_id == revision.faces[1].detection_id
    assert selected.selection_required is False


def test_expired_revision_and_naive_clock_are_rejected() -> None:
    now = datetime(2026, 7, 28, tzinfo=UTC)
    store = DetectionRevisionStore(clock=lambda: now, ttl=timedelta(seconds=1))
    revision = store.create(
        actor_id="actor-a",
        role=ImageRole.SOURCE,
        detector_id=DETECTOR_ID,
        content_sha256="d" * 64,
        width=100,
        height=80,
        faces=(),
    )
    now += timedelta(seconds=2)
    assert store.get_for_actor(revision.revision_id, "actor-a") is None

    naive = DetectionRevisionStore(clock=lambda: datetime(2026, 7, 28))
    with pytest.raises(ValueError, match="timezone-aware"):
        naive.create(
            actor_id="actor-a",
            role=ImageRole.SOURCE,
            detector_id=DETECTOR_ID,
            content_sha256="e" * 64,
            width=1,
            height=1,
            faces=(),
        )


def test_explicit_invalidation_clears_only_the_requested_actor_role() -> None:
    store = DetectionRevisionStore()
    source = store.create(
        actor_id="actor-a",
        role=ImageRole.SOURCE,
        detector_id=DETECTOR_ID,
        content_sha256="f" * 64,
        width=100,
        height=80,
        faces=(),
    )
    target = store.create(
        actor_id="actor-a",
        role=ImageRole.TARGET,
        detector_id=DETECTOR_ID,
        content_sha256="0" * 64,
        width=100,
        height=80,
        faces=(),
    )

    store.invalidate("actor-a", ImageRole.SOURCE)

    assert store.get_for_actor(source.revision_id, "actor-a") is None
    assert store.get_for_actor(target.revision_id, "actor-a") == target


def test_task_pair_requires_exact_actor_bytes_and_selected_faces() -> None:
    store = DetectionRevisionStore()
    source_face = face(10)
    target_face = face(50)
    source = store.create(
        actor_id="actor-a",
        role=ImageRole.SOURCE,
        detector_id=DETECTOR_ID,
        content_sha256="1" * 64,
        width=100,
        height=80,
        faces=(source_face,),
    )
    target = store.create(
        actor_id="actor-a",
        role=ImageRole.TARGET,
        detector_id=DETECTOR_ID,
        content_sha256="2" * 64,
        width=100,
        height=80,
        faces=(target_face,),
    )

    verified = store.validate_task_pair(
        actor_id="actor-a",
        source_revision_id=source.revision_id,
        source_detection_id=source_face.detection_id,
        source_content_sha256="1" * 64,
        target_revision_id=target.revision_id,
        target_detection_id=target_face.detection_id,
        target_content_sha256="2" * 64,
    )
    assert verified.detector_id == DETECTOR_ID
    assert verified.source_detection_id == source_face.detection_id
    assert verified.target_detection_id == target_face.detection_id

    with pytest.raises(DetectionRevisionError) as wrong_actor:
        store.validate_task_pair(
            actor_id="actor-b",
            source_revision_id=source.revision_id,
            source_detection_id=source_face.detection_id,
            source_content_sha256="1" * 64,
            target_revision_id=target.revision_id,
            target_detection_id=target_face.detection_id,
            target_content_sha256="2" * 64,
        )
    assert wrong_actor.value.code == "detection_revision_invalid"

    with pytest.raises(DetectionRevisionError) as wrong_bytes:
        store.validate_task_pair(
            actor_id="actor-a",
            source_revision_id=source.revision_id,
            source_detection_id=source_face.detection_id,
            source_content_sha256="9" * 64,
            target_revision_id=target.revision_id,
            target_detection_id=target_face.detection_id,
            target_content_sha256="2" * 64,
        )
    assert wrong_bytes.value.code == "detection_image_mismatch"

    with pytest.raises(DetectionRevisionError) as wrong_face:
        store.validate_task_pair(
            actor_id="actor-a",
            source_revision_id=source.revision_id,
            source_detection_id="face_00000000000000000000",
            source_content_sha256="1" * 64,
            target_revision_id=target.revision_id,
            target_detection_id=target_face.detection_id,
            target_content_sha256="2" * 64,
        )
    assert wrong_face.value.code == "face_selection_invalid"
