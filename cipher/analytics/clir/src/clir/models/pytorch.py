"""HuggingFace model wrapper with separated preprocessing and inference."""

from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from transformers import (
    AutoModel,
    AutoTokenizer,
    PreTrainedModel,
    PreTrainedTokenizerBase,
)
from transformers.utils import is_flash_attn_2_available

from cipher.schemas._base.common import ModelDevice
from clir.models.base import Model
from clir.models.registry import ModelConfig, get_model_config_from_name
from clir.schemas import ConversationChunkTokenized


def _resolve_attn_implementation() -> str:
    """Determines the best attention implementation available.

    1. flash_attention_2: If package is installed and hardware (Ampere+) supports it.
    2. sdpa: Built-in PyTorch 2.x "Accelerated Transformers" (no install needed).
    3. eager: Standard PyTorch (slowest, highest memory).
    """
    if is_flash_attn_2_available():
        return "flash_attention_2"

    # Check if PyTorch version is 2.0 or higher for SDPA
    if hasattr(torch.nn.functional, "scaled_dot_product_attention"):
        return "sdpa"

    return "eager"


def _resolve_dtype(device: str) -> torch.dtype:
    """Use bfloat16 for modern GPUs, float32 otherwise."""
    if device == "cuda" and torch.cuda.is_available():
        major, _ = torch.cuda.get_device_capability()
        if major >= 8:
            return torch.bfloat16
    return torch.float32


class TextEmbeddingPytorchModel(Model):
    def __init__(
        self,
        model_dir: Path,
        device: ModelDevice | None = None,
        default_max_seq_length: int | None = None,
        config: ModelConfig | None = None,
    ):
        self.load(
            model_dir=model_dir,
            device=device,
            default_max_seq_length=default_max_seq_length,
            config=config,
        )

    def load(
        self,
        model_dir: Path,
        device: ModelDevice | None = None,
        default_max_seq_length: int | None = None,
        config: ModelConfig | None = None,
    ) -> None:
        """Load the model and tokenizer."""
        model_dir = Path(model_dir)
        assert model_dir.exists(), f"Model directory {model_dir} does not exist."

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        if config is None:
            config = get_model_config_from_name(model_dir)
        self.config = config

        dtype = _resolve_dtype(device)
        attn_impl = _resolve_attn_implementation()

        self.model: PreTrainedModel = AutoModel.from_pretrained(
            model_dir,
            local_files_only=True,
            trust_remote_code=True,
            dtype=dtype,
            attn_implementation=attn_impl,
        ).to(device)

        self.tokenizer: PreTrainedTokenizerBase = AutoTokenizer.from_pretrained(
            model_dir, use_fast=True, local_files_only=True, trust_remote_code=True
        )

        self.default_max_seq_length = default_max_seq_length or self.tokenizer.model_max_length

    def unload(self) -> None:
        """Unload the model from memory."""
        del self.model
        del self.tokenizer
        torch.cuda.empty_cache()

    def _get_task_id(self, task: str) -> int:
        """Lookup for LoRA task IDs from the model config."""
        lora_adaptations = getattr(self.model.config, "lora_adaptations", None)
        if not lora_adaptations:
            return None
        if task not in lora_adaptations:
            raise ValueError(f"Task '{task}' not found in model lora_adaptations.")
        return lora_adaptations.index(task)

    def preprocess(
        self,
        batch: list[str],
        is_query: bool = True,
        max_length: int | None = None,
        **tokenizer_kwargs,
    ) -> dict:
        """Tokenize a batch of texts with the appropriate prompt template and return model inputs."""
        # Jina v5 strictly expects 'Query: ' or 'Document: ' (Title Case)
        prefix = "Query: " if is_query else "Document: "
        text_batch = [f"{prefix}{t}" for t in batch]

        max_length = max_length or self.default_max_seq_length

        return self.tokenizer(
            text_batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=max_length,
            **tokenizer_kwargs,
        )

    def preprocess_post_tokenization(
        self,
        chunks: list[ConversationChunkTokenized],
    ) -> dict[str, torch.Tensor]:
        """Takes the output of MessageChunker and prepares a batch for the GPU."""
        # 1. Collate the individual chunk tensors into a padded batch
        max_len = max(c.input_ids.shape[0] for c in chunks)
        batch_size = len(chunks)

        # Use the model's actual pad token
        pad_id = self.tokenizer.pad_token_id if self.tokenizer.pad_token_id is not None else 0

        input_ids = torch.full((batch_size, max_len), pad_id, dtype=torch.long)
        attention_mask = torch.zeros(batch_size, max_len, dtype=torch.long)

        for i, chunk in enumerate(chunks):
            length = chunk.input_ids.shape[0]
            input_ids[i, :length] = chunk.input_ids
            attention_mask[i, :length] = chunk.attention_mask

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }

    def infer(
        self,
        inputs: dict[str, torch.Tensor],
        task: str = "retrieval",
        truncate_dim: int | None = None,
    ) -> np.ndarray:
        """Run the model forward pass and return embeddings. Expects preprocessed inputs."""
        device_inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # CRITICAL: This is the Jina v5 way of handling 'tasks'
        # It swaps the underlying LoRA weights for the specific batch
        if hasattr(self.model, "set_adapter"):
            self.model.set_adapter([task])

        self.model.eval()
        with torch.inference_mode():
            outputs = self.model(**device_inputs)
            hidden = outputs.last_hidden_state
            mask = device_inputs.get("attention_mask")

            # LAST-TOKEN POOLING (The Jina v5 Standard)
            if mask is None:
                pooled = hidden[:, -1]
            else:
                # Find the last 1 in the attention mask
                sequence_lengths = mask.sum(dim=1) - 1
                pooled = hidden[
                    torch.arange(hidden.shape[0], device=hidden.device),
                    sequence_lengths,
                ]

            if truncate_dim is not None:
                pooled = pooled[:, :truncate_dim]

            # Normalize in float32 even when inference runs in bfloat16 (modern GPUs, see
            # _resolve_dtype) -- bf16's ~3-decimal-digit precision leaves the result's
            # magnitude off by up to ~0.2%, which downstream consumers relying on a strict
            # unit-length vector (e.g. Elasticsearch's dot_product similarity, tolerance
            # ~1e-4) reject outright. Normalizing in float32 brings it to exactly 1.0.
            embeddings = F.normalize(pooled.float(), p=2, dim=-1)

        return embeddings.detach().cpu().float().numpy()

    def encode(
        self,
        batch: list[str],
        task: str = "retrieval",
        is_query: bool = True,
        max_length: int | None = None,
    ) -> np.ndarray:
        """Convenience wrapper combining both stages."""
        inputs = self.preprocess(batch, is_query=is_query, max_length=max_length)
        return self.infer(inputs, task=task)
