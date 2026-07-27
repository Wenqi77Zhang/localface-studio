"""Replaceable face detector boundary for native and future research adapters."""

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from localface_studio.domain.faces import DetectedFace

FaceImage = NDArray[np.uint8]


class FaceDetector(Protocol):
    """Detect faces without persisting pixels, landmarks, or identity embeddings."""

    @property
    def detector_id(self) -> str:
        """Return the stable model profile ID used in metadata and task state."""
        ...

    def detect(self, image: FaceImage) -> tuple[DetectedFace, ...]:
        """Return deterministic results in original-image coordinates."""
        ...
