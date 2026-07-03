from pathlib import Path

import torch
import torch.nn.functional as F
import transformers
from loguru import logger
from transformers import AutoTokenizer

from clir.models.base import Model
from clir.schemas import Device
from clir.utils.embedding import pool_pt

try:
    from optimum.onnxruntime import ORTModelForFeatureExtraction
except ImportError as exc:
    raise ImportError(
        "Please install onnx to use the OnnxModel. "
        "You can do this by running `pip install optimum[onnxruntime] or optimum[onnxruntime-gpu]`."
    ) from exc

transformers.logging.set_verbosity(transformers.logging.CRITICAL)


class OnnxModel(Model):
    def __init__(
        self,
        model_dir: Path,
        device: Device,
        warmup: bool = False,
        quantized: bool = False,
        default_max_seq_length: int = None,
        **kwargs,
    ):
        self.load(
            model_dir=model_dir, device=device, warmup=warmup, quantized=quantized
        )

    def load(
        self,
        model_dir: Path,
        device: Device,
        warmup: bool = False,
        quantized: bool = False,
        default_max_seq_length: int = None,
    ):
        file_name = None
        possible_files = [f.relative_to(model_dir) for f in model_dir.rglob("*.onnx")]
        desired_filename = "model_quantized.onnx" if quantized else "model.onnx"
        assert desired_filename in [f.name for f in possible_files], (
            f"Model {desired_filename} not found in {model_dir}"
        )
        file_relative_path = next(
            f for f in possible_files if f.name == desired_filename
        )

        provider = (
            "CPUExecutionProvider" if device == Device.cpu else "CUDAExecutionProvider"
        )
        logger.debug(f"Loading model from {model_dir} and {file_name=} onto {device}")

        self.model = ORTModelForFeatureExtraction.from_pretrained(
            model_dir,
            file_name=file_relative_path,
            local_files_only=True,
            execution_provider=provider,
        ).to(device)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_dir, local_files_only=True, use_fast=True
        )
        self.model_dir = model_dir
        self.device = self.model.device
        logger.info(f"Loaded model from {model_dir} and {file_name=} onto {device}")

        if warmup:
            logger.info("Warming up model")
            self.infer(["Hello world!"])

        self.default_max_seq_length = (
            default_max_seq_length
            if default_max_seq_length
            else self.tokenizer.model_max_length
        )

    def unload(self):
        self.model.to("cpu")
        del self.model
        del self.tokenizer
        torch.cuda.empty_cache()

    def infer(self, batch: list[str], normalized: bool = True, max_length: int = None):
        """Infer embeddings for a batch of passages"""
        max_length = max_length or self.default_max_seq_length
        with torch.inference_mode():
            inputs = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=max_length,
            ).to(self.device)
            outputs = self.model(**inputs)
            pooled = pool_pt(
                outputs.last_hidden_state, inputs.attention_mask, method="avg"
            )
            if normalized:
                pooled = F.normalize(pooled, p=2, dim=1)
        return pooled.cpu().numpy()
