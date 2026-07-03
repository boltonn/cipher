import math
from pathlib import Path

import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image

from cipher.schemas.common import ModelDevice
from cipher.schemas.detection import BoundingBox
from cipher.schemas.face import FaceAnnotation, FaceLandmarks5
from face.utils.align import is_face_backwards
from face.utils.detection import normalize
from face.utils.embedding import normalize as normalize_embedding


class InsightFaceModel:
    """Face detection and analysis model using InsightFace."""

    def __init__(
        self,
        model_dir: Path,
        device: ModelDevice,
        det_thresh: float = 0.5,
        det_size: tuple[int] = (640, 640),
    ):
        providers = ["CPUExecutionProvider"] if device == ModelDevice.CPU else ["CUDAExecutionProvider"]
        self.model = FaceAnalysis(root=model_dir, providers=providers, name="buffalo_l")
        self.model.prepare(ctx_id=0, det_thresh=det_thresh, det_size=det_size)

    @staticmethod
    def standardize(face: dict, height: int, width: int, min_size: int = 30) -> FaceAnnotation:
        """Standardize the output of InsightFace to FaceAnnotation schema."""
        # landmarks are allowed to be outside 0-1 range as they are not used for cropping but could be estimates of where the landmarks would be
        return {
            "bbox": dict(
                zip(
                    BoundingBox.model_fields.keys(),
                    normalize(face["bbox"], height=height, width=width, apply_boundary=True),
                    strict=False,
                )
            ),
            "confidence": face["det_score"],
            "landmarks": dict(
                zip(
                    FaceLandmarks5.model_fields.keys(),
                    normalize(face["kps"].flatten(), height=height, width=width),
                    strict=False,
                )
            ),
            "embedding": normalize_embedding(face["embedding"]),
            "attributes": {
                "age": face["age"],
                "sex": {0: "female", 1: "male"}[face["gender"]],
                "pose": {
                    "pitch": math.degrees(math.asin(math.sin(math.radians(face["pose"][0])))),
                    "yaw": -math.degrees(math.asin(math.sin(math.radians(face["pose"][1])))),
                    "roll": math.degrees(math.asin(math.sin(math.radians(face["pose"][2])))),
                },
            },
        }

    def infer(
        self,
        img: Image.Image,
        min_conf: float = 0.3,
        min_size: int = 30,
    ) -> list[FaceAnnotation]:
        """Infer faces from an image.

        Args:
            img (Image.Image): Image to infer faces from.
            min_conf (float, optional): Minimum confidence to consider a face. Defaults to 0.3.
            min_size (int, optional): Minimum size both dimensions of a face must be for an embedding to be associated. Defaults to 30.
        """
        img = img.convert("RGB")
        width, height = img.size
        # RGB to BGR for model
        img = np.array(img)[..., ::-1]
        faces = self.model.get(img)
        faces = [InsightFaceModel.standardize(f, height=height, width=width, min_size=min_size) for f in faces]
        return [f for f in faces if not is_face_backwards(f) and f["confidence"] >= min_conf]
