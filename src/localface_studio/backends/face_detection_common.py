"""Shared fail-closed validation for local face detector adapters."""

import numpy as np

from localface_studio.application.face_detection import FaceImage


class FaceDetectionError(RuntimeError):
    """Expected detector failure with a stable non-sensitive error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_face_image(image: FaceImage) -> tuple[int, int]:
    """Return image height and width after strict BGR uint8 validation."""
    if not isinstance(image, np.ndarray):
        raise FaceDetectionError("face_detection_image_invalid")
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise FaceDetectionError("face_detection_image_invalid")
    height, width = image.shape[:2]
    if height < 1 or width < 1:
        raise FaceDetectionError("face_detection_image_invalid")
    return height, width
