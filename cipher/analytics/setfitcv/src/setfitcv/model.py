import gc
from pathlib import Path
from typing import TYPE_CHECKING

import torch
from loguru import logger
from PIL import Image
from transformers import CLIPImageProcessor, CLIPModel, CLIPTokenizer
from transformers.modeling_outputs import BaseModelOutputWithPooling

from cipher.schemas._base.common import ModelDevice

if TYPE_CHECKING:
    from setfitcv.heads import TagHeads


class CLIP:
    def __init__(self, model_dir: Path, device: ModelDevice = None, warmup: bool = True):
        if device is not None and device not in ModelDevice:
            raise ValueError(f"Invalid device specified: {device}")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.debug(f"Loading CLIP model on device: {self.device}")
        self.model_dir = model_dir
        self.model = CLIPModel.from_pretrained(model_dir, local_files_only=True).to(self.device)
        self.tokenizer = CLIPTokenizer.from_pretrained(model_dir, local_files_only=True)
        self.img_preprocessor = CLIPImageProcessor.from_pretrained(model_dir, local_files_only=True)
        if warmup:
            self.warmup()

    def warmup(self):
        """Warmup the model with dummy data to initialize GPU kernels."""
        dummy_img = torch.randn(1, 3, 224, 224).to(self.device)
        dummy_txt = torch.randint(0, 1000, (1, 16)).to(self.device)

        with torch.inference_mode():
            self.model.get_image_features(pixel_values=dummy_img)
            self.model.get_text_features(input_ids=dummy_txt)

    def decommission(self):
        """Decommission the model and free up resources."""
        self.model.to("cpu")
        del self.model
        torch.cuda.empty_cache()
        gc.collect()

    def preprocess_txt(self, texts: list[str]):
        """Preprocess text inputs into token IDs.

        Done on CPU.
        """
        return self.tokenizer(texts, return_tensors="pt", padding=True)

    def preprocess_imgs(self, imgs: list[Image.Image]):
        """Preprocess image inputs into pixel values.

        Done on CPU.
        """
        return self.img_preprocessor(images=imgs, return_tensors="pt")["pixel_values"]

    def embed_txt_batch(self, batched_tensors: torch.Tensor, normalized: bool = True):
        """GPU Inference of text embeddings for a batch of token ID tensors."""
        inputs = {"input_ids": batched_tensors.to(self.device)}
        with torch.inference_mode():
            embeddings = _projected(self.model.get_text_features(**inputs))
            if normalized:
                embeddings = torch.nn.functional.normalize(embeddings, dim=1)
        return embeddings.cpu().tolist()

    def embed_imgs_batch(self, pixel_values: torch.Tensor, normalized: bool = True):
        """GPU Inference of image embeddings for a batch of pixel value tensors."""
        inputs = {"pixel_values": pixel_values.to(self.device)}
        with torch.inference_mode():
            embeddings = _projected(self.model.get_image_features(**inputs))
            if normalized:
                embeddings = torch.nn.functional.normalize(embeddings, dim=1)
        return embeddings.cpu().tolist()

    def embed_and_score_imgs_batch(
        self, pixel_values: torch.Tensor, heads: "TagHeads"
    ) -> tuple[list[list[float]], list[dict[str, float]]]:
        """Normalized embeddings plus every tag head's score, in one GPU pass (heads add one matmul)."""
        inputs = {"pixel_values": pixel_values.to(self.device)}
        with torch.inference_mode():
            embeddings = torch.nn.functional.normalize(_projected(self.model.get_image_features(**inputs)), dim=1)
            scores = heads.score_tensor(embeddings)
        return embeddings.cpu().tolist(), heads.as_dicts(scores.cpu().numpy())


def _projected(features: torch.Tensor | BaseModelOutputWithPooling) -> torch.Tensor:
    """The projected CLIP embedding: transformers>=5 wraps it in `pooler_output`, 4.x returns the tensor."""
    return features if isinstance(features, torch.Tensor) else features.pooler_output
