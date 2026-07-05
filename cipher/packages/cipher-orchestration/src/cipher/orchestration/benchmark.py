"""Benchmark Postgres as the extracted-text cache.

extract_documents.py/extract_emails.py persist the expensive-to-produce
result of parsing/OCR once, in Postgres, so nothing downstream ever has to
re-run extraction to get at the text. This empirically answers "is that
caching layer itself slow, or does it use meaningful disk space" -- by
measuring real upsert/read latency and on-disk size for rows shaped like
real extraction output, rather than guessing from column types alone.
Compare the write/read numbers here against `pyxberg benchmark`'s
per-file extraction time to see which one actually dominates end to end.
"""

import random
import statistics
import string
from time import perf_counter
from typing import TYPE_CHECKING

from sqlalchemy import text

from cipher.datastores.postgres.repositories import (
    PostgresDatasetRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
)
from cipher.schemas.dataset import DatasetCreate
from cipher.schemas.document import DocumentMetadata, ExtractedTableInfo
from cipher.schemas.extraction import ExtractedTextCreate, ExtractionContentFormat, TextExtractor
from cipher.schemas.file import FileCreate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _random_text(n_chars: int) -> str:
    words = ["".join(random.choices(string.ascii_lowercase, k=random.randint(3, 9))) for _ in range(n_chars // 6)]
    return " ".join(words)


def _fake_extracted_text(file_id: str, content_chars: int, n_tables: int) -> ExtractedTextCreate:
    """Build a payload shaped like a real extractor's output for an OCR'd multi-page PDF."""
    metadata = DocumentMetadata(
        filename="benchmark.pdf",
        title="Benchmark Document",
        authors=["Benchmark Author"],
        page_count=10,
        detected_language="en",
        tables=[
            ExtractedTableInfo(
                cells=[[f"r{r}c{c}" for c in range(5)] for r in range(8)],
                markdown="| a | b | c | d | e |\n|---|---|---|---|---|\n" * 8,
                page_number=i + 1,
            )
            for i in range(n_tables)
        ]
        or None,
    )
    return ExtractedTextCreate(
        file_id=file_id,
        content=_random_text(content_chars),
        content_format=ExtractionContentFormat.MARKDOWN,
        extractor=TextExtractor.KREUZBERG,
        metadata=metadata,
    )


def _stats(times_ms: list[float]) -> dict:
    return {
        "mean_ms": round(statistics.mean(times_ms), 3),
        "median_ms": round(statistics.median(times_ms), 3),
        "p95_ms": round(statistics.quantiles(times_ms, n=20)[18], 3) if len(times_ms) >= 20 else round(max(times_ms), 3),
        "min_ms": round(min(times_ms), 3),
        "max_ms": round(max(times_ms), 3),
    }


async def benchmark_storage(
    session: "AsyncSession",
    n: int = 100,
    content_chars: int = 35_000,
    n_tables: int = 2,
    cleanup: bool = True,
) -> dict:
    """Benchmark Postgres upsert/read latency and on-disk size for n synthetic ExtractedText rows.

    Defaults (~35k chars, 2 tables) approximate a real ~10-page OCR'd PDF.
    Creates a throwaway `benchmark-storage-*` dataset with n fake File rows
    to satisfy the FK, deleted afterward unless cleanup=False.
    """
    dataset_repo = PostgresDatasetRepository(session=session)
    file_repo = PostgresFileRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)

    dataset = await dataset_repo.add_dataset(DatasetCreate(name=f"benchmark-storage-{int(perf_counter() * 1000)}"))

    file_ids = []
    for i in range(n):
        file = await file_repo.upsert_file(
            FileCreate(
                filename=f"benchmark-{i}.pdf",
                filetype="pdf",
                filetype_group="document",
                md5=f"{i:032x}",
                sha256=f"{i:064x}",
                mime_type="application/pdf",
                path=f"/tmp/benchmark-{i}.pdf",
                uri=f"file:///tmp/benchmark-{i}.pdf",
                size=content_chars,
                dataset_id=dataset.id,
            )
        )
        file_ids.append(file.id)

    write_times_ms = []
    for file_id in file_ids:
        payload = _fake_extracted_text(file_id, content_chars=content_chars, n_tables=n_tables)
        start = perf_counter()
        await extracted_text_repo.upsert(payload)
        write_times_ms.append((perf_counter() - start) * 1000)

    read_times_ms = []
    for file_id in file_ids:
        start = perf_counter()
        await extracted_text_repo.get_by_file_id(file_id)
        read_times_ms.append((perf_counter() - start) * 1000)

    table_size_bytes = (await session.execute(text("SELECT pg_total_relation_size('extracted_text')"))).scalar_one()

    if cleanup:
        await session.execute(text("DELETE FROM dataset WHERE id = :id"), {"id": dataset.id})
        await session.commit()

    return {
        "n": n,
        "content_chars_per_row": content_chars,
        "tables_per_row": n_tables,
        "write": write_times_ms and _stats(write_times_ms),
        "read": read_times_ms and _stats(read_times_ms),
        "extracted_text_table_size_bytes": table_size_bytes,
        "extracted_text_table_size_mb": round(table_size_bytes / 1_000_000, 2),
        "dataset_id": dataset.id if not cleanup else None,
    }
