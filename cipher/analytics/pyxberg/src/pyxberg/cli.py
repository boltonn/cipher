"""CLI for extracting text/tables/structure from a local file via xberg."""

import json
import statistics
from pathlib import Path
from time import perf_counter
from typing import Annotated

import typer
from loguru import logger

app = typer.Typer(help="Extract text, tables, and structure from a local file using xberg.")


@app.command("extract")
def extract(
    path: Annotated[Path, typer.Argument(help="File to extract")],
    disable_ocr: Annotated[bool, typer.Option(help="Skip OCR entirely")] = False,
    ocr_language: Annotated[str, typer.Option(help="OCR language code, e.g. 'eng', 'deu'")] = "eng",
    show_tables: Annotated[bool, typer.Option(help="Print extracted tables as markdown")] = False,
):
    """Extract a single file and print its content, metadata, and table/language/page summary."""
    from kreuzberg import ExtractionConfig, OcrConfig, extract_file_sync

    config = ExtractionConfig(disable_ocr=disable_ocr, ocr=OcrConfig(language=ocr_language))
    result = extract_file_sync(str(path), config=config)

    typer.echo(result.content)

    logger.info(f"Detected language: {result.get_detected_language()}")
    logger.info(f"Page count: {result.get_page_count()}")
    logger.info(f"Tables found: {len(result.tables or [])}")

    if show_tables:
        for i, table in enumerate(result.tables or []):
            typer.echo(f"\n--- Table {i} (page {table.page_number}) ---")
            typer.echo(table.markdown)


@app.command("benchmark")
def benchmark(
    directory: Annotated[Path, typer.Argument(help="Directory of files to benchmark extraction over")],
    disable_ocr: Annotated[bool, typer.Option(help="Skip OCR entirely")] = False,
    ocr_language: Annotated[str, typer.Option(help="OCR language code, e.g. 'eng', 'deu'")] = "eng",
    glob: Annotated[str, typer.Option(help="Glob pattern for files to include")] = "**/*",
    report: Annotated[Path | None, typer.Option(help="Write a per-file JSON report to this path")] = None,
):
    """Measure xberg's per-file extraction time over a directory.

    Existence-of-a-baseline, not a claim of what's fast: the point is to have
    real numbers on hand for this codebase's own files if/when comparing
    against another extractor (e.g. unstructured.io) later.
    """
    from kreuzberg import ExtractionConfig, OcrConfig, extract_file_sync

    config = ExtractionConfig(disable_ocr=disable_ocr, ocr=OcrConfig(language=ocr_language))
    paths = [p for p in sorted(directory.glob(glob)) if p.is_file()]
    if not paths:
        raise typer.BadParameter(f"No files found under {directory} matching {glob!r}")

    rows = []
    for path in paths:
        size_bytes = path.stat().st_size
        start = perf_counter()
        try:
            result = extract_file_sync(str(path), config=config)
            elapsed_ms = (perf_counter() - start) * 1000
            rows.append(
                {
                    "path": str(path),
                    "size_bytes": size_bytes,
                    "extraction_ms": round(elapsed_ms, 1),
                    "content_length": len(result.content),
                    "page_count": result.get_page_count(),
                    "error": None,
                }
            )
        except Exception as e:
            elapsed_ms = (perf_counter() - start) * 1000
            rows.append(
                {
                    "path": str(path),
                    "size_bytes": size_bytes,
                    "extraction_ms": round(elapsed_ms, 1),
                    "content_length": None,
                    "page_count": None,
                    "error": str(e),
                }
            )
        typer.echo(f"{rows[-1]['extraction_ms']:>8.1f}ms  {size_bytes:>10} bytes  {path.name}")

    ok_rows = [r for r in rows if r["error"] is None]
    times = [r["extraction_ms"] for r in ok_rows]
    total_bytes = sum(r["size_bytes"] for r in ok_rows)
    total_ms = sum(times)

    typer.echo("\n--- Summary ---")
    typer.echo(f"Files: {len(rows)} ({len(rows) - len(ok_rows)} failed)")
    if times:
        typer.echo(f"Total: {total_ms / 1000:.2f}s over {total_bytes / 1_000_000:.2f}MB")
        typer.echo(f"Throughput: {(total_bytes / 1_000_000) / (total_ms / 1000):.2f} MB/s")
        typer.echo(
            f"Per-file ms: mean={statistics.mean(times):.1f} "
            f"median={statistics.median(times):.1f} "
            f"min={min(times):.1f} max={max(times):.1f}"
        )

    if report is not None:
        report.write_text(
            json.dumps({"config": {"disable_ocr": disable_ocr, "ocr_language": ocr_language}, "files": rows}, indent=2)
        )
        typer.echo(f"\nWrote per-file report to {report}")


if __name__ == "__main__":
    app()
