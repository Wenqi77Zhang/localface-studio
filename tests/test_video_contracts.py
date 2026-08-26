"""Video extension contracts remain strict and biometric-minimal."""

import numpy as np
import pytest

from localface_studio.application.video_contracts import VideoCheckpoint, VideoFrame


def test_video_frame_requires_monotonic_coordinate_shape() -> None:
    frame = VideoFrame(0, 0.0, np.zeros((12, 16, 3), dtype=np.uint8))
    assert frame.pixels.shape == (12, 16, 3)
    with pytest.raises(ValueError, match="coordinates"):
        VideoFrame(-1, 0.0, frame.pixels)
    with pytest.raises(ValueError, match="HxWx3"):
        VideoFrame(0, 0.0, np.zeros((12, 16), dtype=np.uint8))


def test_checkpoint_contains_progress_but_no_biometric_field() -> None:
    checkpoint = VideoCheckpoint("task", "a" * 64, 12, ("fragment-000",))
    assert checkpoint.next_frame_index == 12
    assert not hasattr(checkpoint, "embedding")
    assert not hasattr(checkpoint, "identity_vector")
    with pytest.raises(ValueError, match="identity"):
        VideoCheckpoint("task", "short", 0)
