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
import shutil
import statistics
import string
import tempfile
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from sqlalchemy import text

from cipher.datastores.postgres.repositories import (
    PostgresDatasetRepository,
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
)
from cipher.orchestration.extract_documents import extract_documents_workflow
from cipher.orchestration.extract_emails import extract_emails_workflow
from cipher.orchestration.ingest import load_files
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


def _throughput(count: int, elapsed_ms: float) -> float | None:
    return round(count / (elapsed_ms / 1000), 2) if elapsed_ms and count else None


async def benchmark_ingest(
    session: "AsyncSession",
    directory: Path,
    file_analyzer: Callable,
    limit: int | None = None,
    skip_emails: bool = False,
    skip_documents: bool = False,
    cleanup: bool = True,
) -> dict:
    """Benchmark real end-to-end ingest throughput over a local directory.

    Unlike `benchmark_storage` (synthetic Postgres rows) or `pyxberg
    benchmark` (raw xberg extraction, no DB), this times the actual
    `load_files` / `extract_emails_workflow` / `extract_documents_workflow`
    functions against a disposable dataset -- so it reflects real
    filetyping/hashing/DB-write cost, and any optimization made to those
    functions shows up here automatically without the benchmark itself
    needing to change. Creates a throwaway `benchmark-ingest-*` dataset,
    purged the same way `DELETE /datasets/{id}` does (enrichments first, no
    real FK) unless `cleanup=False`. Email attachments are extracted into a
    fresh temp directory rather than next to `directory`'s source files, so
    re-running this benchmark never mutates the directory being measured.
    """
    dataset_repo = PostgresDatasetRepository(session=session)
    file_repo = PostgresFileRepository(session=session)
    enrichment_repo = PostgresEnrichmentRepository(session=session)

    dataset = await dataset_repo.add_dataset(DatasetCreate(name=f"benchmark-ingest-{int(perf_counter() * 1000)}"))
    result: dict = {"directory": str(directory)}

    start = perf_counter()
    file_count = await load_files(
        session=session, path=directory, dataset_id=dataset.id, file_analyzer=file_analyzer, limit=limit
    )
    load_ms = (perf_counter() - start) * 1000

    inventory = await file_repo.get_dataset_inventory(dataset.id)
    total_bytes = sum(info["size_bytes"] for info in inventory.values())
    result["load_files"] = {
        "files": file_count,
        "total_ms": round(load_ms, 1),
        "files_per_sec": _throughput(count=file_count, elapsed_ms=load_ms),
        "mb_per_sec": round((total_bytes / 1_000_000) / (load_ms / 1000), 2) if load_ms else None,
        "by_filetype_group": {group: info["count"] for group, info in inventory.items()},
    }

    attachments_dir = Path(tempfile.mkdtemp(prefix="benchmark-ingest-attachments-"))
    try:
        if not skip_emails:
            start = perf_counter()
            email_count = await extract_emails_workflow(
                session=session, dataset_id=dataset.id, attachments_dir=attachments_dir
            )
            email_ms = (perf_counter() - start) * 1000
            result["extract_emails"] = {
                "emails": email_count,
                "total_ms": round(email_ms, 1),
                "emails_per_sec": _throughput(count=email_count, elapsed_ms=email_ms),
            }

        if not skip_documents:
            start = perf_counter()
            doc_count = await extract_documents_workflow(session=session, dataset_id=dataset.id)
            doc_ms = (perf_counter() - start) * 1000
            result["extract_documents"] = {
                "documents": doc_count,
                "total_ms": round(doc_ms, 1),
                "documents_per_sec": _throughput(count=doc_count, elapsed_ms=doc_ms),
            }
    finally:
        shutil.rmtree(attachments_dir, ignore_errors=True)

    result["dataset_id"] = dataset.id if not cleanup else None
    if cleanup:
        await enrichment_repo.delete_by_dataset_files(dataset.id)
        await dataset_repo.delete_dataset(dataset.id)

    return result
