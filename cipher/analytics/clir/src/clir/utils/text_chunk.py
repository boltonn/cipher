"""Plain-text chunking for CLIR workflows -- documents and emails.

Unlike MessageChunker (which concatenates pre-tokenized message boundaries
and has no notion of character offsets into a single source string), this
operates on one flat block of extracted text and needs real start/end
character offsets for highlighting -- so it tokenizes with
`return_offsets_mapping=True` directly rather than reusing langchain's
splitter, which only returns chunk text, not offsets against the original
string.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from transformers import AutoTokenizer, PreTrainedTokenizerBase


@dataclass(frozen=True, slots=True)
class TextChunkSpan:
    content: str
    start_offset: int
    end_offset: int
    token_count: int


class PlainTextChunker:
    """Token-budget chunker for a single block of extracted text.

    A final chunk below `min_chunk_tokens` is merged into the previous one
    rather than dropped or embedded on its own -- silently losing the tail
    of a document would make search incomplete, and a slightly-over-budget
    last chunk is a smaller cost than losing content entirely.
    """

    def __init__(
        self,
        tokenizer: PreTrainedTokenizerBase,
        chunk_size: int | None = None,
        chunk_overlap: int = 0,
        min_chunk_tokens: int = 0,
    ):
        model_max = tokenizer.model_max_length
        if chunk_size is not None and chunk_size > model_max:
            raise ValueError(f"chunk_size {chunk_size} exceeds model max sequence length {model_max}")

        self.tokenizer = tokenizer
        self.chunk_size = chunk_size or model_max
        self.chunk_overlap = chunk_overlap
        self.min_chunk_tokens = min_chunk_tokens

        special = tokenizer("", add_special_tokens=True)
        self.token_budget = self.chunk_size - len(special["input_ids"])

    @classmethod
    def from_pretrained(cls, model_name_or_path: str | Path, **kwargs) -> "PlainTextChunker":
        """Convenience constructor to load a tokenizer from a local directory."""
        tokenizer = AutoTokenizer.from_pretrained(
            str(model_name_or_path),
            use_fast=True,
            local_files_only=isinstance(model_name_or_path, Path),
            trust_remote_code=True,
        )
        return cls(tokenizer=tokenizer, **kwargs)

    def chunk(self, text: str) -> Iterator[TextChunkSpan]:
        """Split text into token-budget-respecting spans with real character offsets."""
        if not text:
            return

        encoding = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True, truncation=False)
        offsets = encoding["offset_mapping"]
        n = len(offsets)
        if n == 0:
            return

        step = max(self.token_budget - self.chunk_overlap, 1)
        pending: TextChunkSpan | None = None

        i = 0
        while i < n:
            end = min(i + self.token_budget, n)
            start_char, end_char = offsets[i][0], offsets[end - 1][1]
            token_count = end - i

            if pending is not None and token_count < self.min_chunk_tokens:
                pending = TextChunkSpan(
                    content=text[pending.start_offset : end_char],
                    start_offset=pending.start_offset,
                    end_offset=end_char,
                    token_count=pending.token_count + token_count,
                )
            else:
                if pending is not None:
                    yield pending
                pending = TextChunkSpan(
                    content=text[start_char:end_char],
                    start_offset=start_char,
                    end_offset=end_char,
                    token_count=token_count,
                )

            if end == n:
                break
            i += step

        if pending is not None:
            yield pending
