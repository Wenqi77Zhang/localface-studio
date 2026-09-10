"""Model-independent, injectable boundaries for single-face processing."""

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from localface_studio.domain.faces import DetectedFace


@dataclass(frozen=True, slots=True)
class SwapOutput:
    image: NDArray[np.uint8]
    execution_providers: tuple[str, ...]


class FaceSwapper(Protocol):
    """Replace exactly the selected target, without writing files or keeping identities."""

    def swap(
        self,
        source: NDArray[np.uint8],
        target: NDArray[np.uint8],
        source_face: DetectedFace,
        target_face: DetectedFace,
    ) -> SwapOutput: ...

    def capabilities(self) -> dict[str, object]: ...


class FaceEnhancer(Protocol):
    """Produce a separate optional derivative; never overwrite the base image."""

    enhancer_id: str

    def enhance(
        self,
        target: NDArray[np.uint8],
        base: NDArray[np.uint8],
        target_face: DetectedFace,
    ) -> NDArray[np.uint8]: ...
