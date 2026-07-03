from dataclasses import dataclass

from pydantic import ConfigDict, Field
from torch import Tensor

from cipher.schemas.base import BaseModel
from cipher.schemas.message import Message


@dataclass
class ConversationChunkTokenized:
    """Pre-built chunk ready for GPU inference — no text re-tokenization needed.

    Produced by MessageChunker by concatenating per-message token ID tensors.
    The tensors are 1D (no batch dimension) — the embedding step stacks a batch
    of these and pads them together before sending to the model.

    Fields
    ------
    messages      : original Message objects, preserved for the final schema
    input_ids     : (seq_len,) — concatenated token IDs for all messages
    attention_mask: (seq_len,) — all ones; padding is added at inference time
    sep_token_id  : the separator token ID inserted between messages, if any
    """

    messages: list[Message]
    input_ids: Tensor  # (seq_len,)
    attention_mask: Tensor  # (seq_len,)


class EmbeddingsRequest(BaseModel):
    text: str = Field(..., description="Text to embed")
    normalized: bool = Field(
        False, description="Whether to normalize the embedding vector"
    )
    chunk_size: int = Field(None, description="Chunk size for text splitting")
    chunk_overlap: int = Field(0, description="Chunk overlap for text splitting")
    max_chunks: int = Field(5, description="Maximum number of chunks to generate")
    average: bool = Field(
        True, description="Whether to average the embeddings of all chunks"
    )
    model_config: ConfigDict = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "他能在多大程度上对此施加影响是很重要的，因为无论结果如何，他都将难脱干系。",
                    "normalized": False,
                    "chunk_size": None,
                    "chunk_overlap": 0,
                    "max_chunks": 5,
                    "average": True,
                },
                {
                    "text": "how did Alex get to the store",
                    "normalized": True,
                    "chunk_size": 512,
                    "chunk_overlap": 0,
                    "max_chunks": 5,
                    "average": False,
                },
            ]
        }
    }
