"""Message chunking utility for CLIR workflows.

No text is re-tokenized during chunking. The output ConversationChunkTokenized
carries pre-built input_ids/attention_mask tensors ready for GPU inference.
Text fields are reconstructed from the original Message objects only when
needed (for BM25 / display in the final ConversationChunk).
"""

from collections.abc import Iterator
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import torch
from clir.models.registry import ModelConfig
from clir.schemas import ConversationChunkTokenized
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer, PreTrainedTokenizerBase

from cipher.schemas.content.message import MessageBase


@lru_cache(maxsize=1)
def get_chunker(
    tokenizer: PreTrainedTokenizerBase,
    chunk_size: int | None = None,
    chunk_overlap: int = 0,
) -> RecursiveCharacterTextSplitter:
    """Get a langchain RecursiveCharacterTextSplitter configured for the model/tokenizer."""
    return RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
        tokenizer=tokenizer,
        chunk_size=chunk_size or tokenizer.model_max_length,
        chunk_overlap=chunk_overlap,
    )


class MessageChunker:
    """Chunk messages by operating directly on token ID tensors.

    Workflow per conversation:
      1. Batch-tokenize all messages at once via tokenize_conversation()
      2. Call chunk_tokenized() to yield ConversationChunkTokenized objects
         by concatenating the pre-built tensors — zero redundant tokenization

    The token budget correctly accounts for:
      - Model max sequence length
      - Special tokens added by the tokenizer (CLS, EOS, etc.)
      - Separator tokens inserted between messages
      - An optional prompt prefix (e.g. "query: " for E5 models)

    Strategies:
        token   : split when concatenated length would exceed the budget
        count   : split after max_messages_per_chunk messages
        time    : split on time gaps between messages
        hybrid  : time windows first, then token-split within each window
    """

    def __init__(
        self,
        config: ModelConfig,
        tokenizer: PreTrainedTokenizerBase,
        strategy: Literal["token", "count", "time", "hybrid"] = "token",
        chunk_size: int | None = None,
        max_messages_per_chunk: int | None = None,
        min_messages_per_chunk: int = 0,
        overlap_messages: int = 0,
        time_window_minutes: int | None = None,
        separator: str = "\n",
        use_translation: bool = False,
    ):
        self.config = config
        self.tokenizer = tokenizer
        self.strategy = strategy
        self.max_messages_per_chunk = max_messages_per_chunk
        self.min_messages_per_chunk = min_messages_per_chunk
        self.overlap_messages = overlap_messages
        self.time_window = timedelta(minutes=time_window_minutes) if time_window_minutes else None
        self.use_translation = use_translation

        model_max = tokenizer.model_max_length
        if chunk_size is not None:
            if chunk_size <= 0:
                raise ValueError("chunk_size must be positive")
            if chunk_size > model_max:
                raise ValueError(f"chunk_size {chunk_size} exceeds model max sequence length {model_max}")
        self.chunk_size = chunk_size or model_max

        # Compute fixed token overheads that reduce the budget per chunk.
        # We tokenize with add_special_tokens=True on an empty string to find
        # how many special tokens the model always adds (CLS, EOS, etc.)
        special = tokenizer("", add_special_tokens=True, return_tensors="pt")
        self._special_token_ids: torch.Tensor = special["input_ids"][0]  # e.g. [CLS, EOS]
        n_special = self._special_token_ids.shape[0]

        prompt_text = self.config.passage_template
        self._prompt_ids: torch.Tensor = self._encode_raw(prompt_text)
        # length of the prefix prompt in tokens that goes at the start of every chunk (e.g. "Document: ")
        n_prompt = self._prompt_ids.shape[0]

        sep_ids = self._encode_raw(separator)
        self._sep_ids: torch.Tensor = sep_ids
        self._sep_len: int = sep_ids.shape[0]

        # Budget = chunk_size minus everything that isn't message content
        self._token_budget: int = self.chunk_size - n_special - n_prompt

    @property
    def _sep_attention(self) -> torch.Tensor:
        return torch.ones(self._sep_len, dtype=torch.long)

    def _encode_raw(self, text: str) -> torch.Tensor:
        """Encode text without special tokens, return 1D input_ids tensor."""
        return self.tokenizer(
            text,
            add_special_tokens=False,
            return_tensors="pt",
        )["input_ids"][0]

    def _message_text(self, msg: MessageBase) -> str | None:
        return msg.translation if (self.use_translation and msg.translation) else msg.text

    def _message_timestamp(self, msg: MessageBase) -> datetime | None:
        return msg.date_received or msg.date_sent

    @classmethod
    def from_pretrained(
        cls,
        model_name_or_path: str | Path,
        **kwargs,
    ) -> "MessageChunker":
        """Convenience constructor to load a tokenizer from HuggingFace and create a MessageChunker."""
        tokenizer = AutoTokenizer.from_pretrained(
            str(model_name_or_path),
            use_fast=True,
            local_files_only=isinstance(model_name_or_path, Path),
            trust_remote_code=True,
        )
        return cls(tokenizer=tokenizer, **kwargs)

    def tokenize_conversation(
        self,
        messages: list[MessageBase],
    ) -> dict[str, torch.Tensor]:
        """Batch-tokenize all messages in a conversation.

        Returns a dict mapping message_id -> 1D input_ids tensor (no special
        tokens, no padding). This is the only tokenization call for the entire
        conversation — chunking concatenates these tensors directly.
        """
        texts = [self._message_text(msg) or "" for msg in messages]

        # This call is internally multi-threaded in Rust.
        # Removing return_tensors="pt" avoids the ValueError you saw.
        encoded = self.tokenizer(
            texts,
            add_special_tokens=False,
            truncation=True,
            max_length=self._token_budget,
        )

        return {
            msg.message_id: torch.tensor(ids, dtype=torch.long)
            for msg, ids in zip(messages, encoded["input_ids"], strict=True)
        }

    def chunk_tokenized(
        self,
        messages: list[MessageBase],
        token_map: dict[str, torch.Tensor],
    ) -> Iterator[ConversationChunkTokenized]:
        """Yield ConversationChunkTokenized by concatenating token tensors.

        No tokenization happens here — just tensor concatenation and slicing.
        Special tokens and prompt are prepended once per chunk at yield time.
        """
        if self.strategy == "token":
            yield from self._chunk_by_tokens(messages, token_map)
        elif self.strategy == "count":
            if not self.max_messages_per_chunk:
                raise ValueError("max_messages_per_chunk required for count strategy")
            yield from self._chunk_by_count(messages, token_map)
        elif self.strategy == "time":
            if not self.time_window:
                raise ValueError("time_window_minutes required for time strategy")
            yield from self._chunk_by_time(messages, token_map)
        elif self.strategy == "hybrid":
            if not (self.max_messages_per_chunk and self.time_window):
                raise ValueError("hybrid requires max_messages_per_chunk and time_window_minutes")
            yield from self._chunk_by_hybrid(messages, token_map)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    def chunk_messages(
        self,
        messages: list[MessageBase],
    ) -> Iterator[ConversationChunkTokenized]:
        """Convenience: tokenize then chunk in one call."""
        token_map = self.tokenize_conversation(messages)
        yield from self.chunk_tokenized(messages, token_map)

    def _build_chunk(
        self,
        chunk_messages: list[MessageBase],
        token_map: dict[str, torch.Tensor],
    ) -> ConversationChunkTokenized:
        """Concatenate token tensors for a group of messages into one chunk.

        Layout: [special_prefix] [prompt] [msg0] [SEP] [msg1] [SEP] ... [msgN] [special_suffix]

        Special tokens are split into prefix (e.g. CLS) and suffix (e.g. EOS)
        by checking their position in the empty-string encoding.
        """
        parts: list[torch.Tensor] = []

        # Separate prefix specials (CLS) from suffix specials (EOS/SEP at end)
        # We do this by re-encoding a dummy token and seeing what wraps it
        dummy = self.tokenizer("x", add_special_tokens=True, return_tensors="pt")["input_ids"][0]
        dummy_no_special = self._encode_raw("x")
        # Find where the content token sits in the full encoding
        content_start = (dummy == dummy_no_special[0]).nonzero(as_tuple=True)[0]
        content_start = content_start[0].item() if len(content_start) else 0
        prefix_specials = dummy[:content_start]
        suffix_specials = dummy[content_start + len(dummy_no_special) :]

        if prefix_specials.numel():
            parts.append(prefix_specials)
        if self._prompt_ids.numel():
            parts.append(self._prompt_ids)

        for i, msg in enumerate(chunk_messages):
            if i > 0 and self._sep_ids.numel():
                parts.append(self._sep_ids)
            ids = token_map.get(msg.message_id)
            if ids is not None and ids.numel():
                parts.append(ids)

        if suffix_specials.numel():
            parts.append(suffix_specials)

        input_ids = torch.cat(parts)

        # # --- DEBUG START ---
        # # This will print the actual text the model is about to "see"
        # decoded = self.tokenizer.decode(input_ids, skip_special_tokens=False)
        # print(
        #     f"\n[DEBUG CHUNK] Messages: {len(chunk_messages)} | Tokens: {len(input_ids)}"
        # )
        # print(f"Content: {decoded[:200]}...")  # Print first 200 chars
        # print("-" * 20)
        # # --- DEBUG END ---

        attention_mask = torch.ones(input_ids.shape[0], dtype=torch.long)

        return ConversationChunkTokenized(
            messages=chunk_messages,
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

    def _token_len(self, msg: MessageBase, token_map: dict[str, torch.Tensor]) -> int:
        ids = token_map.get(msg.message_id)
        return ids.shape[0] if ids is not None else 0

    def _chunk_by_tokens(
        self,
        messages: list[MessageBase],
        token_map: dict[str, torch.Tensor],
    ) -> Iterator[ConversationChunkTokenized]:
        chunk: list[MessageBase] = []
        lengths: list[int] = []
        n_total = 0

        for msg in messages:
            n = self._token_len(msg, token_map)
            if not n:
                continue
            cost = n + (self._sep_len if chunk else 0)

            if n_total + cost > self._token_budget and chunk:
                if len(chunk) >= self.min_messages_per_chunk:
                    yield self._build_chunk(chunk, token_map)
                if self.overlap_messages and len(chunk) > self.overlap_messages:
                    chunk = chunk[-self.overlap_messages :]
                    lengths = lengths[-self.overlap_messages :]
                    n_total = sum(lengths)
                else:
                    chunk, lengths, n_total = [], [], 0

            chunk.append(msg)
            lengths.append(cost)
            n_total += cost

        if chunk:
            yield self._build_chunk(chunk, token_map)

    def _chunk_by_count(
        self,
        messages: list[MessageBase],
        token_map: dict[str, torch.Tensor],
    ) -> Iterator[ConversationChunkTokenized]:
        i = 0
        while i < len(messages):
            end = min(i + self.max_messages_per_chunk, len(messages))
            yield self._build_chunk(messages[i:end], token_map)
            i = end - self.overlap_messages if self.overlap_messages else end

    def _chunk_by_time(
        self,
        messages: list[MessageBase],
        token_map: dict[str, torch.Tensor],
    ) -> Iterator[ConversationChunkTokenized]:
        current: list[MessageBase] = []
        start_time: datetime | None = None

        for msg in messages:
            msg_time = self._message_timestamp(msg)
            if msg_time is None:
                current.append(msg)
                continue
            if start_time is None:
                start_time = msg_time

            time_exceeded = msg_time - start_time > self.time_window
            count_exceeded = self.max_messages_per_chunk and len(current) >= self.max_messages_per_chunk

            if (time_exceeded or count_exceeded) and current:
                yield self._build_chunk(current, token_map)
                current = current[-self.overlap_messages :] if self.overlap_messages else []
                start_time = msg_time

            current.append(msg)

        if current:
            yield self._build_chunk(current, token_map)

    def _chunk_by_hybrid(
        self,
        messages: list[MessageBase],
        token_map: dict[str, torch.Tensor],
    ) -> Iterator[ConversationChunkTokenized]:
        for time_chunk in self._chunk_by_time(messages, token_map):
            yield from self._chunk_by_tokens(time_chunk.messages, token_map)
