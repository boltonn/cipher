"""The models pyvllm serves: one `vllm serve` process each, all from the same install."""

import json
from dataclasses import dataclass, field

# The jina plugin's image token and FastMTP heads (deepseek_ocr_mtp.vllm_llm_kwargs).
_JINA_IMAGE_TOKEN_INDEX = 128815


@dataclass(frozen=True)
class ModelSpec:
    """How to serve one model.

    Attributes:
        name: Short handle used by the CLI and jobs (`llm`, `ocr`).
        model: Hugging Face repo id or local directory passed to `vllm serve`.
        served_name: Model name clients send in requests.
        port: Port of its OpenAI-compatible API.
        gpu: GPU index it runs on (`CUDA_VISIBLE_DEVICES`).
        gpu_memory_utilization: Share of that GPU vLLM may claim.
        args: Further `vllm serve` flags.
    """

    name: str
    model: str
    served_name: str
    port: int
    gpu: int
    gpu_memory_utilization: float
    args: list[str] = field(default_factory=list)

    @property
    def base_url(self) -> str:
        """Root URL of the model's OpenAI-compatible API."""
        return f"http://localhost:{self.port}"


MODELS: dict[str, ModelSpec] = {
    # Always-on assistant for chat, pyprompt and extract-llm. The 4-bit build fits one 3090
    # with ~25k tokens of KV cache, so one request may use 24k (agent runs of 6+ tool calls
    # overflowed 16k). Its checkpoint asks for an fp8 KV cache, which Ampere can't run
    # (FlashAttention needs SM90+, FlashInfer's JIT needs a newer nvcc), hence bf16 KV.
    "llm": ModelSpec(
        name="llm",
        model="/home/boltonn/models/RedHatAI/Qwen3.8-27B-INT4",
        served_name="Qwen/Qwen3.8-27B",
        port=8008,
        gpu=1,
        gpu_memory_utilization=0.93,
        args=[
            "--max-model-len",
            "24576",
            "--max-num-seqs",
            "16",
            "--attention-backend",
            "FLASH_ATTN",
            "--kv-cache-dtype",
            "bfloat16",
            "--enable-auto-tool-choice",
            "--tool-call-parser",
            "qwen3_xml",
            "--reasoning-parser",
            "qwen3",
            "--default-chat-template-kwargs",
            json.dumps({"enable_thinking": False}),
        ],
    ),
    # Page OCR, started on demand by `cipher ocr`; leaves room on its GPU for the other analytics.
    "ocr": ModelSpec(
        name="ocr",
        model="jinaai/jina-ocr-v1",
        served_name="jinaai/jina-ocr-v1",
        port=8010,
        gpu=0,
        gpu_memory_utilization=0.45,
        args=[
            "--trust-remote-code",
            "--dtype",
            "bfloat16",
            "--max-model-len",
            "8192",
            "--max-num-seqs",
            "128",
            # speculative decoding otherwise caps a step at 2048 tokens, starving page prefill
            "--max-num-batched-tokens",
            "8192",
            "--limit-mm-per-prompt",
            json.dumps({"image": 1}),
            "--hf-overrides",
            json.dumps(
                {
                    "architectures": ["DeepseekOCRForCausalLMOCR"],
                    "num_nextn_predict_layers": 1,
                    "mtp_recursive": True,
                    "image_token_index": _JINA_IMAGE_TOKEN_INDEX,
                }
            ),
            "--speculative-config",
            json.dumps({"model": "jinaai/jina-ocr-v1", "num_speculative_tokens": 3, "method": "eagle"}),
        ],
    ),
}
