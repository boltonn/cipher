"""Chunk and embed messages from a parquet file and save to a new parquet."""

import tempfile
from collections.abc import Iterator
from enum import StrEnum
from itertools import groupby
from pathlib import Path
from typing import Annotated

import numpy as np
import pandas as pd
import polars as pl
import typer
from clir.models.pytorch import TextEmbeddingPytorchModel
from clir.models.registry import get_model_config_from_name
from clir.schemas import ConversationChunkTokenized
from clir.utils.chunk import MessageChunker
from pydantic import TypeAdapter
from tqdm import tqdm

from cipher.schemas.content.message import ConversationChunk, MessageBase

app = typer.Typer(help="Chunk (and optionally embed) mobile messages from a parquet file.")

REQUIRED_COLUMNS = list(MessageBase.model_json_schema(by_alias=False)["properties"].keys())

_message_adapter = TypeAdapter(list[MessageBase])


class Strategy(StrEnum):
    token = "token"
    count = "count"
    time = "time"
    hybrid = "hybrid"


def sort_parquet(source: Path, dest: Path) -> None:
    """Sort the input parquet by conversation_id and date_received for better chunking performance."""
    schema_cols = pl.read_parquet_schema(source).names()
    selected_cols = [c for c in REQUIRED_COLUMNS if c in schema_cols]
    sort_cols = [c for c in ("conversation_id", "date_received") if c in schema_cols]

    pl.scan_parquet(source).sort(sort_cols).select(selected_cols or pl.all()).sink_parquet(dest)


def _iter_batches(path: Path, batch_size: int) -> Iterator[list[dict]]:
    available = pl.read_parquet_schema(path).names()
    columns = [c for c in REQUIRED_COLUMNS if c in available] or None
    for batch in pl.read_parquet(path, columns=columns).iter_slices(batch_size):
        for col in ("date_sent", "date_received", "date_read"):
            if col in batch.columns:
                batch = batch.with_columns(pl.col(col).cast(pl.Datetime("us", "UTC"), strict=False))
        yield batch.to_dicts()


def run_optimized(
    sorted_path: Path, chunker: MessageChunker, total_rows: int, batch_size: int
) -> Iterator[ConversationChunkTokenized]:
    """Run the optimized chunking pipeline with progress tracking."""
    with tqdm(total=total_rows, desc="Messages", unit="msg", position=0) as msg_bar:
        for raw_batch in _iter_batches(sorted_path, batch_size):
            messages = _message_adapter.validate_python(raw_batch)
            token_map = chunker.tokenize_conversation(messages=messages)
            for _conv_id, group_iter in groupby(messages, key=lambda r: r.conversation_id):
                conv_messages = list(group_iter)
                yield from chunker.chunk_tokenized(conv_messages, token_map)
                msg_bar.update(len(conv_messages))


def embed_chunks(
    chunks: Iterator[ConversationChunkTokenized],
    model: TextEmbeddingPytorchModel,
    task: str,
    total_chunks_bar: tqdm,
    embed_batch_size: int = 16,
) -> Iterator[ConversationChunk]:
    """Embed conversation chunks in batches with progress tracking."""
    buffer = []

    def flush(batch):
        inputs = model.preprocess_post_tokenization(batch)
        embeddings_np = model.infer(inputs, task=task)
        total_chunks_bar.update(len(batch))
        return [
            ConversationChunk(messages=chunk.messages, embedding=emb.tolist())
            for chunk, emb in zip(batch, embeddings_np, strict=True)
        ]

    for chunk in chunks:
        buffer.append(chunk)
        if len(buffer) >= embed_batch_size:
            yield from flush(buffer)
            buffer.clear()
    if buffer:
        yield from flush(buffer)


@app.command()
def main(
    parquet: Annotated[Path, typer.Argument(exists=True)],
    model_dir: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option(help="Path to save embedded chunks")] = Path("chunks.parquet"),
    device: Annotated[str | None, typer.Option()] = None,
    task: Annotated[str | None, typer.Option()] = "retrieval",
    embed_batch_size: Annotated[int, typer.Option()] = 32,
    chunk_size: Annotated[int | None, typer.Option()] = 512,
    batch_size: Annotated[int, typer.Option()] = 50_000,
) -> None:
    """Chunk and embed messages from a parquet file."""
    model = TextEmbeddingPytorchModel(model_dir=model_dir, device=device)
    model_config = get_model_config_from_name(model_dir)
    chunker = MessageChunker(config=model_config, tokenizer=model.tokenizer, chunk_size=chunk_size)
    total_rows = pl.scan_parquet(parquet).select(pl.len()).collect().item()

    with tempfile.TemporaryDirectory() as tmpdir:
        sorted_path = Path(tmpdir) / "sorted.parquet"
        typer.echo(f"Sorting {parquet.name}...")
        sort_parquet(parquet, sorted_path)

        chunk_stream = run_optimized(sorted_path, chunker, total_rows, batch_size)

        results = []

        with tqdm(desc="Embedding", unit="chunk", position=1) as embed_bar:
            for embedded in embed_chunks(
                chunks=chunk_stream,
                model=model,
                task=task,
                total_chunks_bar=embed_bar,
                embed_batch_size=embed_batch_size,
            ):
                results.append(
                    {
                        "messages": [msg.model_dump(mode="json") for msg in embedded.messages],
                        "embedding": embedded.embedding,
                    }
                )

        if results:
            typer.echo(f"Saving {len(results)} chunks to {output}...")
            df = pd.DataFrame(results)
            df.to_parquet("chunks.parquet", engine="pyarrow")
        else:
            typer.echo("No chunks generated.")

    model.unload()
    typer.echo("Done.")


@app.command()
def search(
    query_text: str,
    parquet_path: Path,
    model_dir: Path,
    task: str = "retrieval",
    top_k: int = 5,
):
    """Search for relevant message chunks based on a query."""
    model = TextEmbeddingPytorchModel(model_dir=model_dir)
    query_vec = model.encode([query_text], is_query=True, task=task)[0]

    df = pd.read_parquet(parquet_path)
    embeddings = np.stack(df["embedding"].to_list())
    scores = embeddings @ query_vec
    top_indices = np.argsort(scores)[::-1][:top_k]

    print(f"\n--- Top {top_k} Results for: '{query_text}' ---\n")

    for idx in top_indices:
        i = int(idx)
        chunk_messages = df["messages"][i]
        chunk_score = scores[i]
        print(f"Score: {chunk_score:.4f}")
        for msg_dict in chunk_messages:
            msg = MessageBase.model_validate(msg_dict)
            print(f"{msg.sender} -> {msg.recipient} | {msg.text}")

        print("-" * 40)


if __name__ == "__main__":
    app()
