import gc
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

# The 5-point landmarks (kps) and bbox come from detection itself, not from
# landmark_2d_106/landmark_3d_68, so landmark_2d_106 is never worth loading.
# landmark_3d_68 (pose) and genderage (age/sex) are opt-in via __init__ flags
# since skipping unused sub-models cuts per-image inference from ~206ms to
# ~66ms (measured on an RTX 3090).
BASE_MODULES = ["detection", "recognition"]


class InsightFaceModel:
    """Face detection and analysis model using InsightFace."""

    def __init__(
        self,
        model_dir: Path,
        device: ModelDevice,
        det_thresh: float = 0.3,
        det_size: tuple[int] = (640, 640),
        get_pose: bool = False,
        get_age_and_sex: bool = False,
    ):
        if device == ModelDevice.CUDA:
            import onnxruntime

            # pip-installed nvidia-cudnn-cu12/nvidia-cublas-cu12 wheels aren't on
            # LD_LIBRARY_PATH by default; this loads their .so files directly so
            # the CUDAExecutionProvider can find libcudnn without env-var setup.
            onnxruntime.preload_dlls()

        self.get_pose = get_pose
        self.get_age_and_sex = get_age_and_sex
        allowed_modules = [
            *BASE_MODULES,
            *(["landmark_3d_68"] if get_pose else []),
            *(["genderage"] if get_age_and_sex else []),
        ]

        providers = ["CPUExecutionProvider"] if device == ModelDevice.CPU else ["CUDAExecutionProvider"]
        self.model = FaceAnalysis(
            root=model_dir, providers=providers, name="buffalo_l", allowed_modules=allowed_modules
        )
        self.model.prepare(ctx_id=0, det_thresh=det_thresh, det_size=det_size)

    def unload(self) -> None:
        """Release the underlying onnxruntime InferenceSessions.

        Each allowed_module owns its own onnxruntime session and thread
        pool; deleting them here (instead of leaving it to interpreter-exit
        GC) lets onnxruntime tear its native semaphores down deterministically,
        which avoids `resource_tracker: leaked semaphore objects` warnings on
        process shutdown.
        """
        del self.model
        gc.collect()

    def standardize(self, face: dict, height: int, width: int) -> FaceAnnotation:
        """Standardize the output of InsightFace to FaceAnnotation schema."""
        # landmarks are allowed to be outside 0-1 range as they are not used for cropping but could be estimates of where the landmarks would be
        annotation: FaceAnnotation = {
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
        }
        if self.get_pose:
            annotation["pose"] = {
                "pitch": math.degrees(math.asin(math.sin(math.radians(face["pose"][0])))),
                "yaw": -math.degrees(math.asin(math.sin(math.radians(face["pose"][1])))),
                "roll": math.degrees(math.asin(math.sin(math.radians(face["pose"][2])))),
            }
        if self.get_age_and_sex:
            annotation["age"] = face["age"]
            annotation["sex"] = {0: "female", 1: "male"}[face["gender"]]
        return annotation

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
        faces = [self.standardize(f, height=height, width=width) for f in faces]
        return [f for f in faces if not is_face_backwards(f) and f["confidence"] >= min_conf]
