from collections.abc import Iterable

import numpy as np


def check_min_size(bbox: Iterable[float | int], min_size: int) -> bool:
    """Check if the face is large enough.

    Args:
        bbox (Iterable[float | int]): Bounding box coordinates.
        min_size (int): Minimum size of the face.
    """
    return (bbox[2] - bbox[0] >= min_size) and (bbox[3] - bbox[1] >= min_size)


def clip_coords(boxes: np.ndarray, height: int, width: int) -> None:
    """Clip bounding xyxy bounding boxes to image shape."""
    boxes[:, 0].clamp_(0, width)  # x1
    boxes[:, 1].clamp_(0, height)  # y1
    boxes[:, 2].clamp_(0, width)  # x2
    boxes[:, 3].clamp_(0, height)  # y2


def crop_np_img(
    img: np.ndarray, bbox: list, normalized: bool = True, scale_factor: float = 1.0
) -> np.ndarray:
    """Crop image based on bounding box.

    Args:
        img (np.ndarray): image to crop
        bbox (list): bounding box in format [xmin, ymin, xmax, ymax]
        normalized (bool): whether the bounding box is normalized
        scale_factor (float): scale factor for zooming in/out the bounding box
            * 1: no zoom
            * 0-1: zoom out
            * 1-2: zoom in
    """
    xmin, ymin, xmax, ymax = zoom_bbox(
        bbox=bbox,
        normalized=normalized,
        scale_factor=scale_factor,
        height=img.shape[0],
        width=img.shape[1],
    )
    return img[int(ymin) : int(ymax), int(xmin) : int(xmax), :]


def normalize(
    points: np.ndarray, height: int, width: int, apply_boundary: bool = False
) -> list[float]:
    """Normalize coordinates that are Nx2.

    Args:
        points (np.ndarray): Points to normalize.
        height (int): Height of the image.
        width (int): Width of the image.
        apply_boundary (bool, optional): Whether to apply boundary conditions (clamp between 0 and 1). Defaults to False.
    """
    out = points.copy()
    for i in range(0, len(out), 2):
        out[i] = out[i] / width
        out[i + 1] = out[i + 1] / height
        if apply_boundary:
            out[i] = min(max(out[i], 0), 1)
            out[i + 1] = min(max(out[i + 1], 0), 1)
    return out


def normalize_boxes(x: np.ndarray, height: int, width: int) -> np.ndarray:
    """Normalize bounding boxes."""
    y = np.copy(x)
    y[:, 0] /= width
    y[:, 1] /= height
    y[:, 2] /= width
    y[:, 3] /= height
    return y


def unnormalize(points: list[float], height: int, width: int) -> list[float]:
    """Unnormalize coordinates."""
    out = points.copy()
    for i in range(0, len(out), 2):
        out[i] = out[i] * width
        out[i + 1] = out[i + 1] * height
    return out


def unnormalize_boxes(x: np.ndarray, height: int, width: int) -> np.ndarray:
    """Unnormalize bounding boxes."""
    y = np.copy(x)
    y[:, 0] *= width
    y[:, 1] *= height
    y[:, 2] *= width
    y[:, 3] *= height
    return y


def xyxy2xywh(x: np.ndarray) -> np.ndarray:
    """Convert nx4 boxes from [x1, y1, x2, y2] to [x, y, w, h] where xy1=top-left, xy2=bottom-right."""
    y = np.copy(x)
    y[:, 0] = (x[:, 0] + x[:, 2]) / 2  # x center
    y[:, 1] = (x[:, 1] + x[:, 3]) / 2  # y center
    y[:, 2] = x[:, 2] - x[:, 0]  # width
    y[:, 3] = x[:, 3] - x[:, 1]  # height
    return y


def xywh2xyxy(x: np.ndarray) -> np.ndarray:
    """Convert nx4 boxes from [x, y, w, h] to [x1, y1, x2, y2] where xy1=top-left, xy2=bottom-right."""
    y = np.copy(x)
    y[:, 0] = x[:, 0] - x[:, 2] / 2  # top left x
    y[:, 1] = x[:, 1] - x[:, 3] / 2  # top left y
    y[:, 2] = x[:, 0] + x[:, 2] / 2  # bottom right x
    y[:, 3] = x[:, 1] + x[:, 3] / 2  # bottom right y
    return y


def xywhn2xyxy(x: np.ndarray, w=640, h=640, padw=32, padh=32):
    """Convert nx4 boxes from [x, y, w, h] normalized to [x1, y1, x2, y2] where xy1=top-left, xy2=bottom-right."""
    y = np.copy(x)
    y[:, 0] = w * (x[:, 0] - x[:, 2] / 2) + padw  # top left x
    y[:, 1] = h * (x[:, 1] - x[:, 3] / 2) + padh  # top left y
    y[:, 2] = w * (x[:, 0] + x[:, 2] / 2) + padw  # bottom right x
    y[:, 3] = h * (x[:, 1] + x[:, 3] / 2) + padh  # bottom right y
    return y


def zoom_bbox(
    bbox,
    normalized: bool = True,
    scale_factor: float = 1.0,
    height: int = None,
    width: int = None,
):
    """Zoom in or out of a bounding box by a scale factor."""
    assert 0 <= scale_factor <= 2, "scale_factor should be in range [0, 2]"
    xmin, ymin, xmax, ymax = bbox

    if normalized:
        xmin, ymin, xmax, ymax = (
            xmin * width,
            ymin * height,
            xmax * width,
            ymax * height,
        )

    zoom_sign = 1 if scale_factor <= 1 else -1
    scale_factor = abs(scale_factor - 1)
    buffer_x = (xmax - xmin) * scale_factor / 2
    buffer_y = (ymax - ymin) * scale_factor / 2
    xmin = max(0, xmin - buffer_x * zoom_sign)
    ymin = max(0, ymin - buffer_y * zoom_sign)
    xmax = min(width, xmax + buffer_x * zoom_sign)
    ymax = min(height, ymax + buffer_y * zoom_sign)
    return xmin, ymin, xmax, ymax
