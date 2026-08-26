"""Ephemeral face detection and single-face selection APIs."""

from datetime import datetime

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from starlette.datastructures import UploadFile
from starlette.responses import JSONResponse

from localface_studio.api.security import require_session
from localface_studio.application.detection_revisions import (
    DetectionRevision,
    DetectionRevisionError,
    DetectionRevisionStore,
    FaceDetectionService,
)
from localface_studio.backends.yunet import YUNET_MODEL_ID
from localface_studio.domain.faces import DetectedFace
from localface_studio.domain.images import ImageRole, ImageUploadError

router = APIRouter(tags=["face-detections"])


class FacePointResponse(BaseModel):
    x: float
    y: float


class FaceBoxResponse(BaseModel):
    x: float
    y: float
    width: float
    height: float


class DetectedFaceResponse(BaseModel):
    detection_id: str
    ordinal: int
    box: FaceBoxResponse
    landmarks: list[FacePointResponse]
    confidence: float


class DetectionRevisionResponse(BaseModel):
    revision_id: str
    role: str
    detector_id: str
    width: int
    height: int
    faces: list[DetectedFaceResponse]
    selected_detection_id: str | None
    selection_required: bool
    expires_at: datetime


class FaceSelectionRequest(BaseModel):
    detection_id: str


@router.post(
    "/face-detections",
    response_model=DetectionRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_detection(
    request: Request,
    response: Response,
) -> DetectionRevisionResponse | JSONResponse:
    """Detect faces in one disposable upload and retain only bounded metadata."""
    async with request.form(max_files=1, max_fields=3, max_part_size=16 * 1024) as form:
        image = form.get("image")
        if not isinstance(image, UploadFile):
            return _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "image_required",
                "An image is required.",
            )
        try:
            role = ImageRole(_form_text(form.get("role"), "source"))
            detector_id = _form_text(form.get("detector_id"), YUNET_MODEL_ID)
            research_license_accepted = _form_boolean(
                form.get("research_license_accepted"),
                False,
            )
        except ValueError as error:
            return _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "invalid_detection_form",
                str(error),
            )
        service: FaceDetectionService = request.app.state.face_detection
        try:
            revision = await service.detect(
                actor_id=request.state.actor_id,
                role=role,
                detector_id=detector_id,
                research_license_accepted=research_license_accepted,
                upload=image,
            )
        except ImageUploadError as error:
            return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, error.code, str(error))
        except DetectionRevisionError as error:
            status_code = (
                status.HTTP_403_FORBIDDEN
                if error.code == "research_model_license_not_accepted"
                else status.HTTP_503_SERVICE_UNAVAILABLE
            )
            return _error(status_code, error.code, str(error))
    response.headers["Cache-Control"] = "no-store"
    return _response(revision)


@router.get(
    "/face-detections/{revision_id}",
    response_model=DetectionRevisionResponse,
)
def get_detection(
    revision_id: str,
    request: Request,
    response: Response,
) -> DetectionRevisionResponse | JSONResponse:
    """Read one live detection revision without exposing other actors' records."""
    session = require_session(request)
    revisions: DetectionRevisionStore = request.app.state.detection_revisions
    revision = revisions.get_for_actor(revision_id, session.actor_id)
    if revision is None:
        return _not_found()
    response.headers["Cache-Control"] = "no-store"
    return _response(revision)


@router.post(
    "/face-detections/{revision_id}/selection",
    response_model=DetectionRevisionResponse,
)
def select_face(
    revision_id: str,
    selection: FaceSelectionRequest,
    request: Request,
    response: Response,
) -> DetectionRevisionResponse | JSONResponse:
    """Select exactly one detected face inside an actor-owned revision."""
    revisions: DetectionRevisionStore = request.app.state.detection_revisions
    try:
        revision = revisions.select(
            revision_id,
            request.state.actor_id,
            selection.detection_id,
        )
    except DetectionRevisionError as error:
        return _error(status.HTTP_409_CONFLICT, error.code, str(error))
    if revision is None:
        return _not_found()
    response.headers["Cache-Control"] = "no-store"
    return _response(revision)


def _response(revision: DetectionRevision) -> DetectionRevisionResponse:
    return DetectionRevisionResponse(
        revision_id=revision.revision_id,
        role=revision.role.value,
        detector_id=revision.detector_id,
        width=revision.width,
        height=revision.height,
        faces=[_face_response(index, face) for index, face in enumerate(revision.faces, 1)],
        selected_detection_id=revision.selected_detection_id,
        selection_required=revision.selection_required,
        expires_at=revision.expires_at,
    )


def _face_response(ordinal: int, face: DetectedFace) -> DetectedFaceResponse:
    return DetectedFaceResponse(
        detection_id=face.detection_id,
        ordinal=ordinal,
        box=FaceBoxResponse(
            x=face.box.x,
            y=face.box.y,
            width=face.box.width,
            height=face.box.height,
        ),
        landmarks=[FacePointResponse(x=point.x, y=point.y) for point in face.landmarks],
        confidence=face.confidence,
    )


def _form_text(value: object, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ValueError("detection fields must be non-empty text")
    return value


def _form_boolean(value: object, default: bool) -> bool:
    if value is None:
        return default
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError("boolean detection fields must be true or false")


def _not_found() -> JSONResponse:
    return _error(
        status.HTTP_404_NOT_FOUND,
        "detection_revision_not_found",
        "Detection revision not found.",
    )


def _error(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "detail": detail})
