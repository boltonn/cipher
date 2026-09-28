"""OCR inference engines: page image in, raw model text out.

`VllmOcrEngine` is the fast path -- vLLM's continuous batching packs every
concurrently-requested page into shared GPU steps, and jina-ocr-v1's FastMTP
head speculatively decodes K tokens per step (~2x). Throughput therefore comes
from keeping many pages in flight, not from batching in the caller.
`TransformersOcrEngine` is a one-page-at-a-time fallback for CPU/dev boxes
without a vLLM install.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from loguru import logger
from PIL import Image
from pydantic import BaseModel, Field

from cipher.schemas._base.common import ModelDevice
from pyocr.parse import DEFAULT_PROMPT, FIGURE_PROMPT
from pyocr.schemas import OcrBackend

DEFAULT_MODEL = "jinaai/jina-ocr-v1"


class EngineConfig(BaseModel):
    model: str = Field(default=DEFAULT_MODEL, description="Hugging Face model id or local snapshot directory")
    backend: OcrBackend = Field(default=OcrBackend.VLLM)
    device: ModelDevice | None = Field(default=None, description="Transformers backend only")
    max_tokens: int = Field(default=4096, description="Generation cap per page")
    num_speculative_tokens: int = Field(default=3, description="vLLM FastMTP draft depth K; 0 disables")
    gpu_memory_utilization: float = Field(default=0.85)
    max_num_seqs: int = Field(default=64, description="vLLM: pages decoded concurrently")
    max_model_len: int = Field(default=8192)
    data_parallel_size: int = Field(default=1, description="vLLM: one engine replica per GPU, load-balanced")


class OcrEngine(Protocol):
    model_name: str

    async def transcribe(self, image: Image.Image, figures: bool = False) -> str:
        """Raw model output for one page image."""
        ...

    def close(self) -> None:
        """Release the model."""
        ...


def resolve_model_dir(model: str) -> Path:
    """Local snapshot for `model` (downloading on first use), so its bundled vLLM plugin can be imported."""
    if Path(model).is_dir():
        return Path(model)
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(model))


class VllmOcrEngine:
    def __init__(self, config: EngineConfig):
        from transformers import AutoTokenizer
        from vllm import AsyncEngineArgs
        from vllm.v1.engine.async_llm import AsyncLLM

        model_dir = resolve_model_dir(config.model)
        # vLLM imports the plugin again in worker subprocesses; the plugin's own
        # path helper resolves HF-cache symlinks into `blobs/`, so export the snapshot dir.
        sys.path.insert(0, str(model_dir))
        os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(model_dir), os.environ.get("PYTHONPATH")]))
        # vLLM 0.30's DeepEncoder attention kernel reads a plain-float global, which triton>=3.7 rejects.
        os.environ.setdefault("TRITON_ALLOW_NON_CONSTEXPR_GLOBALS", "1")
        # FlashInfer's sampler JIT-compiles against the system nvcc; vLLM's own sampler needs no toolchain.
        os.environ.setdefault("VLLM_USE_FLASHINFER_SAMPLER", "0")
        from deepseek_ocr_mtp import prepare_vllm_input, register, vllm_llm_kwargs, vllm_sampling_params

        register()
        kwargs = vllm_llm_kwargs(
            str(model_dir),
            num_speculative_tokens=config.num_speculative_tokens,
            mtp_heads=1,
            mtp_recursive=True,
            gpu_memory_utilization=config.gpu_memory_utilization,
            max_num_seqs=config.max_num_seqs,
            max_model_len=config.max_model_len,
            limit_mm_per_prompt={"image": 1},
            data_parallel_size=config.data_parallel_size,
        )
        self.model_name = config.model
        self._engine = AsyncLLM.from_engine_args(AsyncEngineArgs(**kwargs))
        self._tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
        self._prepare = prepare_vllm_input
        # Keep <|ref|>/<|det|> figure tags (special tokens), as the transformers path does.
        self._sampling = vllm_sampling_params(max_tokens=config.max_tokens, skip_special_tokens=False)

    async def transcribe(self, image: Image.Image, figures: bool = False) -> str:
        """Raw model output for one page image."""
        request = self._prepare(self._tokenizer, image, prompt=FIGURE_PROMPT if figures else DEFAULT_PROMPT)
        final = None
        async for output in self._engine.generate(request, self._sampling, request_id=str(uuid4())):
            final = output
        return final.outputs[0].text if final else ""

    def close(self) -> None:
        """Release the model."""
        self._engine.shutdown()


class TransformersOcrEngine:
    def __init__(self, config: EngineConfig):
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        model_dir = resolve_model_dir(config.model)
        device = config.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model_name = config.model
        self._device = torch.device(device)
        self._processor = AutoProcessor.from_pretrained(model_dir, trust_remote_code=True)
        self._model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.bfloat16, trust_remote_code=True).to(
            self._device
        )
        self._model.eval()
        self._max_tokens = config.max_tokens
        # generate() isn't safe to run concurrently on one model; pages queue here.
        self._lock = asyncio.Lock()

    def _generate(self, image: Image.Image, figures: bool) -> str:
        import torch

        prompt = FIGURE_PROMPT if figures else DEFAULT_PROMPT
        inputs = self._processor.prepare_ocr_inputs(image, prompt=prompt, device=self._device)
        with torch.inference_mode():
            output = self._model.generate(**inputs, max_new_tokens=self._max_tokens, do_sample=False)
        return self._processor.decode_ocr(output, inputs["input_ids"])

    async def transcribe(self, image: Image.Image, figures: bool = False) -> str:
        """Raw model output for one page image."""
        async with self._lock:
            return await asyncio.to_thread(self._generate, image, figures)

    def close(self) -> None:
        """Release the model."""
        import torch

        del self._model
        torch.cuda.empty_cache()


def build_engine(config: EngineConfig) -> OcrEngine:
    """Load the configured backend."""
    logger.info(f"Loading {config.model} on the {config.backend} backend")
    if config.backend == OcrBackend.VLLM:
        return VllmOcrEngine(config)
    return TransformersOcrEngine(config)
