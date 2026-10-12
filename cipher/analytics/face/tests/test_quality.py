import numpy as np
from face.utils.quality import face_quality

FRONTAL = {"lefteye_x": 0.35, "righteye_x": 0.65, "nose_x": 0.5}
PROFILE = {"lefteye_x": 0.45, "righteye_x": 0.55, "nose_x": 0.6}
WHOLE = {"xmin": 0.0, "ymin": 0.0, "xmax": 1.0, "ymax": 1.0}


def _noise(side: int) -> np.ndarray:
    return np.random.default_rng(0).integers(0, 255, (side, side, 3), dtype=np.uint8)


def test_large_sharp_frontal_face_scores_high():
    """A 200 px, high-detail, frontal, confident face is near the top of the scale."""
    assert face_quality(image=_noise(200), bbox=WHOLE, landmarks=FRONTAL, confidence=0.9) > 0.9


def test_tiny_face_scores_zero():
    """Under the useful size, nothing else rescues a face."""
    assert face_quality(image=_noise(14), bbox=WHOLE, landmarks=FRONTAL, confidence=0.9) == 0.0


def test_blur_and_profile_each_lower_the_score():
    """A flat (blurred) crop or a turned head scores below the same face sharp and frontal."""
    sharp = face_quality(image=_noise(200), bbox=WHOLE, landmarks=FRONTAL, confidence=0.9)
    flat = face_quality(image=np.full((200, 200, 3), 128, np.uint8), bbox=WHOLE, landmarks=FRONTAL, confidence=0.9)
    profile = face_quality(image=_noise(200), bbox=WHOLE, landmarks=PROFILE, confidence=0.9)
    assert flat < sharp and profile < sharp
