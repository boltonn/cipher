"""CLI for OCR'ing local files with a local engine (no service needed)."""

import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Annotated

import typer
from loguru import logger

from pyocr.capabilities import SUPPORTED_FILETYPES
from pyocr.engine import DEFAULT_MODEL, EngineConfig, build_engine
from pyocr.pages import DEFAULT_MAX_SIDE, DEFAULT_MIN_CHARS, page_count, scanned_pages
from pyocr.runner import ocr_source
from pyocr.schemas import OcrBackend, OcrRequest

app = typer.Typer(help="Multilingual page OCR for PDFs and images (incl. HEIF).")

_EXTENSIONS = {f".{t}" for t in SUPPORTED_FILETYPES} | {".jpg", ".tif", ".heic"}

ModelOption = Annotated[str, typer.Option(help="HF model id or local snapshot dir")]
BackendOption = Annotated[OcrBackend, typer.Option(help="vllm (fast, needs `make install-vllm`) or transformers")]


def _files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in _EXTENSIONS)


@app.command("triage")
def triage(
    target: Annotated[Path, typer.Argument(help="File or directory")],
    min_chars: Annotated[int, typer.Option(help="Word chars below which a PDF page counts as image-based")] = (
        DEFAULT_MIN_CHARS
    ),
):
    """Show which pages would be OCR'd (image-based PDF pages + images) -- no model needed."""
    total_pages = total_scanned = 0
    for path in _files(target):
        pages, scanned = page_count(path), scanned_pages(path, min_chars=min_chars)
        total_pages += pages
        total_scanned += len(scanned)
        typer.echo(f"{len(scanned):>5}/{pages:<5} {path.name}  {scanned[:20]}{' …' if len(scanned) > 20 else ''}")
    typer.echo(f"\n{total_scanned} of {total_pages} pages need OCR")


@app.command("ocr")
def ocr(
    path: Annotated[Path, typer.Argument(help="PDF or image")],
    pages: Annotated[list[int] | None, typer.Option(help="1-indexed page(s); repeatable")] = None,
    scanned_only: Annotated[bool, typer.Option(help="PDFs: only pages without a text layer")] = False,
    figures: Annotated[bool, typer.Option(help="Locate + caption figures (grounding prompt)")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the full OcrResponse")] = False,
    model: ModelOption = DEFAULT_MODEL,
    backend: BackendOption = OcrBackend.VLLM,
    max_side: int = DEFAULT_MAX_SIDE,
):
    """OCR one file and print its markdown (or JSON with regions)."""
    engine = build_engine(EngineConfig(model=model, backend=backend))
    request = OcrRequest(pages=pages, scanned_only=scanned_only, figures=figures)
    response = asyncio.run(ocr_source(engine=engine, source=path, request=request, max_side=max_side))
    if as_json:
        typer.echo(response.model_dump_json(indent=2))
        return
    for page in response.pages:
        typer.echo(
            f"\n--- page {page.page_number} ({len(page.tables)} tables, {len(page.regions)} figures) ---\n{page.markdown}"
        )


@app.command("benchmark")
def benchmark(
    target: Annotated[Path, typer.Argument(help="Directory of PDFs/images")],
    scanned_only: Annotated[bool, typer.Option(help="PDFs: only pages without a text layer")] = True,
    concurrency: Annotated[int, typer.Option(help="Files in flight at once")] = 16,
    report: Annotated[Path | None, typer.Option(help="Write per-file JSON here")] = None,
    model: ModelOption = DEFAULT_MODEL,
    backend: BackendOption = OcrBackend.VLLM,
    max_side: int = DEFAULT_MAX_SIDE,
):
    """Measure end-to-end pages/s (render + decode) over a directory, many files in flight."""
    files = _files(target)
    if not files:
        raise typer.BadParameter(f"No supported files under {target}")
    engine = build_engine(EngineConfig(model=model, backend=backend))
    request = OcrRequest(scanned_only=scanned_only)

    async def _run() -> list[dict]:
        slots = asyncio.Semaphore(concurrency)

        async def one(path: Path) -> dict:
            async with slots:
                start = perf_counter()
                response = await ocr_source(engine=engine, source=path, request=request, max_side=max_side)
                return {
                    "path": str(path),
                    "pages": len(response.pages),
                    "chars": sum(len(p.markdown) for p in response.pages),
                    "seconds": round(perf_counter() - start, 2),
                }

        return await asyncio.gather(*(one(p) for p in files))

    start = perf_counter()
    rows = asyncio.run(_run())
    elapsed = perf_counter() - start
    pages = sum(r["pages"] for r in rows)
    logger.success(f"{pages} pages from {len(rows)} files in {elapsed:.1f}s -> {pages / elapsed:.2f} pages/s")
    if report:
        report.write_text(json.dumps({"elapsed_seconds": elapsed, "files": rows}, indent=2))


if __name__ == "__main__":
    app()
