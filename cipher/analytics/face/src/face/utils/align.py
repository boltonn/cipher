from typing import Literal

import cv2
import numpy as np
from PIL import Image

from face.utils.detection import zoom_bbox

# NOTE: this is directly integrated in insightface as of 2022 so now keeping for utility purposes like zooming on UI

REFERENCE_FACIAL_LANDMARKS = [
    [38.29459953, 51.69630051],
    [73.53179932, 51.50139999],
    [56.02519989, 71.73660278],
    [41.54930115, 92.3655014],
    [70.72990036, 92.20410156],
]


def _tformfwd(trans, uv):
    """Apply a 2D geometric transformation to an array of 2D points.

    Args:
        trans (np.ndarray): 3x3 matrix representing the geometric transformation.
        uv (np.ndarray): Nx2 array of 2D points.

    Returns:
        xy (np.ndarray): Nx2 array of transformed 2D points.
    """
    uv = np.hstack((uv, np.ones((uv.shape[0], 1))))
    xy = np.dot(uv, trans)
    xy = xy[:, 0:-1]
    return xy


def _find_nonreflective_similarity(uv, xy, options=None):
    """Port of Pytorch face.evoLVE matlab utils."""
    if options is None:
        options = {"K": 2}
    K = options["K"]
    M = xy.shape[0]

    x = xy[:, 0].reshape((-1, 1))
    y = xy[:, 1].reshape((-1, 1))

    tmp1 = np.hstack((x, y, np.ones((M, 1)), np.zeros((M, 1))))
    tmp2 = np.hstack((y, -x, np.zeros((M, 1)), np.ones((M, 1))))
    X = np.vstack((tmp1, tmp2))

    u = uv[:, 0].reshape((-1, 1))
    v = uv[:, 1].reshape((-1, 1))
    U = np.vstack((u, v))

    if np.linalg.matrix_rank(X) >= 2 * K:
        r, _, _, _ = np.linalg.lstsq(X, U, rcond=-1)
        r = np.squeeze(r)
    else:
        raise ValueError("cp2tform: two unique points required")

    sc = r[0]
    ss = r[1]
    tx = r[2]
    ty = r[3]

    Tinv = np.array([[sc, -ss, 0], [ss, sc, 0], [tx, ty, 1]])
    T = np.linalg.inv(Tinv)
    T[:, 2] = np.array([0, 0, 1])
    return T, Tinv


def _find_similarity(uv, xy, options=None):
    """Estimate similarity transform."""
    options = {"K": 2}
    trans1, trans1_inv = _find_nonreflective_similarity(uv, xy, options)

    # Need to reflect the xy data across the Y-axis
    xyR = xy.copy()
    xyR[:, 0] = -1 * xyR[:, 0]
    trans2r, trans2r_inv = _find_nonreflective_similarity(uv, xyR, options)

    TreflectY = np.array([[-1, 0, 0], [0, 1, 0], [0, 0, 1]])
    trans2 = np.dot(trans2r, TreflectY)

    xy1 = _tformfwd(trans1, uv)
    xy2 = _tformfwd(trans2, uv)
    norm1 = np.linalg.norm(xy1 - xy)
    norm2 = np.linalg.norm(xy2 - xy)

    if norm1 < norm2:
        return trans1, trans1_inv
    else:
        trans2_inv = np.linalg.inv(trans2)
        return trans2, trans2_inv


def align_and_crop(
    img: np.ndarray | Image.Image,
    landmarks: np.ndarray,
    bbox: list[float] = None,
    desired_landmarks: np.ndarray = REFERENCE_FACIAL_LANDMARKS,
    scale_factor: float = 0.7,
    crop_size: list | Literal["original"] = None,
    align_type: Literal["similarity", "cv2_affine", "affine"] = "similarity",
    reflective: bool = True,
) -> np.ndarray:
    """Apply affine transformation to align and crop face from image based on facial landmarks.

    Args:
        img (np.ndarray): The source image that contains one or more faces.
        landmarks (np.ndarray): Detected facial landmarks in Kx2 array (x,y) normalized to [0, 1].
        bbox (list[float]): Bounding box of the face in the format [xmin, ymin, xmax, ymax].
        desired_landmarks (np.ndarray): Desired landmarks to warp to unnormalized between 0-255.
        scale_factor (float): 0-1 zoom out factor from crop size.
        crop_size (list[float]|Literal["orginal"]): Desired resolution of the cropped face. Default is [112, 112].
            * "original": Crop the face at the exact size of the bounding box in the source image.
        align_type (str): Type of affine transformation to use. Default is 'similarity'.
            * 'similarity': Similarity transformation.
            * 'cv2_affine': OpenCV's affine transformation using only 3 points. Two eyes and nose tip.
            * 'affine': Affine transformation using all 5 facial landmarks.
        reflective (bool): Whether to use reflective similarity transformation. Default is True.

    Returns:
        np.ndarray: Cropped face image.
    """
    if isinstance(img, Image.Image):
        img = np.array(img)
    if crop_size is None:
        crop_size = [112, 112]

    if crop_size == "original":
        assert bbox is not None, "Bounding box is required when crop_size is 'original'"
        xmin_orig, ymin_orig, xmax_orig, ymax_orig = zoom_bbox(img=img, bbox=bbox, scale_factor=1.0)
        xmin, ymin, xmax, ymax = zoom_bbox(img=img, bbox=bbox, scale_factor=scale_factor, normalized=True)
        crop_size = ((xmax - xmin), (ymax - ymin))
        output_size = np.array(crop_size, dtype=np.float32)
        unscaled_crop_size = np.array((xmax_orig - xmin_orig, ymax_orig - ymin_orig), dtype=np.float32)
        desired_landmarks = np.array(desired_landmarks, dtype=np.float32) * (unscaled_crop_size / 112) + (
            (output_size - unscaled_crop_size) / 2
        )
        # introduces a rounding error but necessary for compatibility with cv2
        crop_size = (round(crop_size[0]), round(crop_size[1]))
    else:
        output_size = np.array(crop_size, dtype=np.float32)
        desired_landmarks = (output_size / 2) - (
            ((output_size / 2) - np.array(desired_landmarks, dtype=np.float32) * (output_size / 112)) * scale_factor
        )
        transform_matrix = None
        if align_type == "cv2_affine":
            transform_matrix = cv2.getAffineTransform(src=landmarks[:3], dst=desired_landmarks[:3])
        elif align_type == "affine":
            transform_matrix = np.float32([[1, 0, 0], [0, 1, 0]])
            n_pts = len(landmarks)
            ones = np.ones((n_pts, 1), dtype=landmarks.dtype)
            landmarks = np.hstack((landmarks, ones))
            desired_landmarks = np.hstack((desired_landmarks, ones))
            A, res, rank, s = np.linalg.lstsq(landmarks, desired_landmarks, rcond=-1)

            if rank == 3:
                transform_matrix = np.float32([[A[0, 0], A[1, 0], A[2, 0]], [A[0, 1], A[1, 1], A[2, 1]]])
            elif rank == 2:
                transform_matrix = np.float32([[A[0, 0], A[1, 0], 0], [A[0, 1], A[1, 1], 0]])
            else:
                raise ValueError("Cannot align face with provided landmarks.")
        else:
            if reflective:
                transform_matrix, _ = _find_similarity(landmarks, desired_landmarks)
            else:
                transform_matrix, _ = _find_nonreflective_similarity(landmarks, desired_landmarks)

            transform_matrix = transform_matrix[:, :2].T
            return cv2.warpAffine(img, transform_matrix, crop_size)


def is_face_backwards(face: dict) -> bool:
    """Check if the face is backwards.

    This was added because insightface sometimes detects faces despite it
    being the backl of someone's head.
    """
    return (
        face["landmarks"]["lefteye_x"] > face["landmarks"]["righteye_x"]
        or face["landmarks"]["leftmouth_x"] > face["landmarks"]["rightmouth_x"]
    )


def convert_radians_to_degrees(radians: float) -> float:
    """Convert radians to degrees between -180 and 180."""
    return radians * (180 / np.pi)
