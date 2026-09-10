"""Tensor-contract checks using injected sessions; no model download in unit tests."""

import sys
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from localface_studio.backends.alphaface import AlphaFaceEngine


class Session:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def get_inputs(self) -> list[Any]:
        return [
            SimpleNamespace(name="source", shape=["batch", 512]),
            SimpleNamespace(name="target", shape=["batch", 3, 256, 256]),
        ]

    def run(self, output: None, inputs: dict[str, np.ndarray]) -> list[np.ndarray]:
        assert inputs["source"].shape == (1, 512)
        assert np.all(inputs["source"] == 7)  # raw, not normalized identity embedding
        assert inputs["target"].dtype == np.float32
        assert inputs["target"].max() <= 1
        return [np.full((1, 3, 256, 256), 0.6, dtype=np.float32)]


def install_runtime(monkeypatch: pytest.MonkeyPatch, session: type[Session] = Session) -> None:
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(InferenceSession=session))
    monkeypatch.setitem(
        sys.modules,
        "insightface.utils.face_align",
        SimpleNamespace(
            norm_crop2=lambda image, points, image_size: (
                image.copy(),
                np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            )
        ),
    )


def test_alphaface_tensor_contract_and_background_blending(monkeypatch: pytest.MonkeyPatch) -> None:
    install_runtime(monkeypatch)
    engine = AlphaFaceEngine("unused-test-path", ["CPUExecutionProvider"])
    target = np.zeros((256, 256, 3), dtype=np.uint8)
    face = SimpleNamespace(kps=np.zeros((5, 2)), embedding=np.full(512, 7, dtype=np.float32))
    result = engine.get(target, face, face, paste_back=True)
    assert result.shape == target.shape
    assert result[140, 128, 0] == 153
    assert np.array_equal(result[0, 0], target[0, 0])
    with pytest.raises(ValueError, match="full-frame"):
        engine.get(target, face, face, paste_back=False)


def test_alphaface_rejects_invalid_tensor(monkeypatch: pytest.MonkeyPatch) -> None:
    class InvalidSession(Session):
        def run(self, output: None, inputs: dict[str, np.ndarray]) -> list[np.ndarray]:
            return [np.full((1, 3, 256, 256), np.nan, dtype=np.float32)]

    install_runtime(monkeypatch, InvalidSession)
    engine = AlphaFaceEngine("test", [])
    face = SimpleNamespace(kps=np.zeros((5, 2)), embedding=np.ones(512))
    with pytest.raises(ValueError, match="invalid tensor"):
        engine.get(np.zeros((256, 256, 3), dtype=np.uint8), face, face, paste_back=True)


@pytest.mark.parametrize("name, shape", [("untrusted", [1, 512]), ("source", [1, 256])])
def test_alphaface_rejects_unknown_model_contract(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    shape: list[int],
) -> None:
    class InvalidSession(Session):
        def get_inputs(self) -> list[Any]:
            return [
                SimpleNamespace(name=name, shape=shape),
                SimpleNamespace(name="target", shape=[1, 3, 256, 256]),
            ]

    install_runtime(monkeypatch, InvalidSession)
    with pytest.raises(ValueError, match="contract"):
        AlphaFaceEngine("test", [])
