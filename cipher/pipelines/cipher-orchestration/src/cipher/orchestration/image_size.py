"""Minimum image size for image analytics -- spacers, tracking pixels and hairlines aren't worth a model pass.

Small images are still ingested (a logo's reuse across emails is evidence); only the analytics skip them.
"""

from pathlib import Path

from PIL import Image

DEFAULT_MIN_IMAGE_SIDE = 64


def is_below_min_side(image: Image.Image | Path, min_side: int) -> bool:
    """True when the image's shorter side is under `min_side` pixels (a path is read header-only)."""
    if isinstance(image, Path):
        with Image.open(image) as opened:
            return min(opened.size) < min_side
    return min(image.size) < min_side
