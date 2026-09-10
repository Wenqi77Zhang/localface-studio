"""Local AlphaFace 256 ONNX adapter (FaceFusion 3.9.0 model input contract).

Original research: https://github.com/andrewyu90/Alphaface_Official
Converted weights: https://github.com/facefusion/facefusion-assets
This module implements preprocessing/compositing locally, without FaceFusion runtime.
"""

from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray


class AlphaFaceEngine:
    """Use unnormalized w600k_r50 identity, RGB [0,1], and ArcFace-128 alignment."""

    def __init__(self, path: str, providers: list[Any]) -> None:
        import onnxruntime as ort

        self.session = ort.InferenceSession(path, providers=providers)
        inputs = {item.name: item.shape for item in self.session.get_inputs()}
        if set(inputs) != {"source", "target"}:
            raise ValueError("AlphaFace model input names do not match the pinned contract")
        if inputs["source"][-1] != 512 or inputs["target"][-2:] != [256, 256]:
            raise ValueError("AlphaFace model input shapes do not match the pinned contract")

    def get(
        self,
        image: NDArray[np.uint8],
        target_face: Any,
        source_face: Any,
        *,
        paste_back: bool,
    ) -> NDArray[np.uint8]:
        if not paste_back:
            raise ValueError("AlphaFace only exports a full-frame result")
        from insightface.utils.face_align import norm_crop2

        crop, matrix = norm_crop2(image, target_face.kps, image_size=256)
        embedding = np.asarray(source_face.embedding, dtype=np.float32).reshape(1, 512)
        tensor = (crop[:, :, ::-1].transpose(2, 0, 1)[None] / 255.0).astype(np.float32)
        generated = np.asarray(self.session.run(None, {"source": embedding, "target": tensor})[0])
        if generated.shape != (1, 3, 256, 256) or not np.isfinite(generated).all():
            raise ValueError("AlphaFace returned an invalid tensor")
        restored = np.clip(generated[0].transpose(1, 2, 0) * 255.0, 0, 255)
        restored = restored[:, :, ::-1].astype(np.uint8)
        return paste_aligned_face(image, restored, matrix)


def paste_aligned_face(
    target: NDArray[np.uint8],
    crop: NDArray[np.uint8],
    matrix: NDArray[np.float64],
) -> NDArray[np.uint8]:
    """Feather only the aligned face interior; preserve exact background pixels."""
    size = crop.shape[0]
    mask = np.zeros((size, size), dtype=np.float32)
    cv2.ellipse(
        mask,
        (size // 2, round(size * 0.56)),
        (round(size * 0.34), round(size * 0.39)),
        0,
        0,
        360,
        1.0,
        -1,
    )
    mask = np.asarray(cv2.GaussianBlur(mask, (0, 0), sigmaX=size * 0.035), dtype=np.float32)
    inverse = cv2.invertAffineTransform(matrix)
    height, width = target.shape[:2]
    # Blend only a bounded ROI instead of allocating two float copies of the full image.
    corners = cv2.transform(
        np.array([[[0, 0], [size, 0], [size, size], [0, size]]], dtype=np.float64), inverse
    )[0]
    x0 = max(0, int(np.floor(corners[:, 0].min())))
    y0 = max(0, int(np.floor(corners[:, 1].min())))
    x1 = min(width, int(np.ceil(corners[:, 0].max())))
    y1 = min(height, int(np.ceil(corners[:, 1].max())))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("aligned face does not intersect image")
    inverse[:, 2] -= (x0, y0)
    pixels = cv2.warpAffine(crop, inverse, (x1 - x0, y1 - y0)).astype(np.float32)
    alpha = cv2.warpAffine(mask, inverse, (x1 - x0, y1 - y0))[:, :, None]
    alpha[alpha < 0.001] = 0
    result = target.copy()
    result[y0:y1, x0:x1] = (
        np.clip(
            pixels * alpha + target[y0:y1, x0:x1] * (1 - alpha),
            0,
            255,
        )
        .round()
        .astype(np.uint8)
    )
    return result
