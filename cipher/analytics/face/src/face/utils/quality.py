"""Face quality: how usable a detected face is for recognition and for showing to an analyst.

A product of four 0-1 factors so any one bad factor sinks the face (a sharp, frontal 12 px face is
still useless):

* resolution -- short side of the face crop in source pixels; full marks at ArcFace's 112 px input
* sharpness  -- Laplacian variance of the crop resized to 112 px (log scale; blur and JPEG mush score low)
* frontal    -- nose offset from the eye midpoint, relative to eye distance (profiles score low)
* confidence -- detector score, full marks from 0.8

Calibrated on the `rag` faces (2026-10-05): median face 59 px, Laplacian median ~65.
"""

import math

import cv2
import numpy as np

ARCFACE_SIDE = 112
MIN_USEFUL_SIDE = 16
FULL_CONFIDENCE = 0.8
PROFILE_YAW_RATIO = 0.6


def face_quality(*, image: np.ndarray, bbox: dict[str, float], landmarks: dict[str, float], confidence: float) -> float:
    """Quality in [0, 1] of one face, from the RGB image and its normalized bbox / 5-point landmarks.

    Args:
        image: RGB (or BGR -- sharpness is colour-blind) array of the whole source image.
        bbox: Normalized `xmin`/`ymin`/`xmax`/`ymax`.
        landmarks: Normalized `lefteye_x`, `righteye_x`, `nose_x`, ... as in `FaceLandmarks5`.
        confidence: Detector score.
    """
    height, width = image.shape[:2]
    x0, y0 = max(int(bbox["xmin"] * width), 0), max(int(bbox["ymin"] * height), 0)
    x1, y1 = min(int(bbox["xmax"] * width), width), min(int(bbox["ymax"] * height), height)
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return 0.0

    resolution = np.clip((min(crop.shape[:2]) - MIN_USEFUL_SIDE) / (ARCFACE_SIDE - MIN_USEFUL_SIDE), 0, 1)
    gray = cv2.cvtColor(cv2.resize(crop, (ARCFACE_SIDE, ARCFACE_SIDE)), cv2.COLOR_RGB2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F).var()
    sharpness = np.clip((math.log10(max(laplacian, 1e-3)) - 0.5) / 2.0, 0, 1)
    eye_distance = abs(landmarks["righteye_x"] - landmarks["lefteye_x"]) * width
    eye_mid = (landmarks["lefteye_x"] + landmarks["righteye_x"]) / 2
    yaw_ratio = abs(landmarks["nose_x"] - eye_mid) * width / max(eye_distance, 1e-6)
    frontal = np.clip(1 - yaw_ratio / PROFILE_YAW_RATIO, 0, 1)
    detector = min(confidence / FULL_CONFIDENCE, 1.0)
    return round(float(resolution * (0.4 + 0.6 * sharpness) * (0.5 + 0.5 * frontal) * detector), 4)
