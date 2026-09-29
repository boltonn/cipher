# pyocr

Multilingual page OCR for PDFs and images (PNG/JPEG/TIFF/WebP/HEIF/…), built around
[jina-ocr-v1](https://huggingface.co/jinaai/jina-ocr-v1) (DeepSeek-OCR backbone, 3B MoE /
~570M active, markdown out). Any DeepSeek-OCR-family checkpoint drops in via `OCR__MODEL`.

> **License:** jina-ocr-v1 weights are **CC BY-NC 4.0** — non-commercial only without a
> commercial agreement from Jina AI.

## How it works

1. **Triage (no model):** `pages.scanned_pages` reads each PDF page's text layer via pdfium
   (milliseconds/page). Pages with fewer than 20 word characters are image-based; only those
   are OCR'd. Every image/TIFF frame counts.
2. **Render:** pdfium (PDF) / Pillow + pillow-heif (images) → RGB, longest side 1600px,
   lazily one page at a time.
3. **Decode:** every page of every in-flight request goes to the engine concurrently.
   - `vllm` (fast): continuous batching + FastMTP speculative decoding (K=3, ~2× decode).
   - `transformers`: one page at a time; dev/CPU fallback.
4. **Parse:** markdown; HTML tables → `ExtractedTableInfo` (inlined back as pipe tables);
   with `figures=true` (DeepSeek grounding prompt) figures come back as `OcrRegion`s with a
   normalized `BoundingBox` + model caption. jina-ocr-v1 emits no per-block boxes — tested, the
   `<|grounding|>Convert the document to markdown.` prompt returns plain text.

## Run

```bash
make download-deps           # hf download jinaai/jina-ocr-v1
make install-vllm            # separate .venv-vllm: vLLM pins its own torch
make start-vllm              # http://localhost:8010  (make start = transformers backend)
make start-vllm-all          # one service per GPU: :8010, :8011 ... (GPUS=0,1)
```

```bash
pyocr triage ./scans/                       # which pages need OCR, no model
pyocr ocr scan.pdf --scanned-only --json    # local engine, no service
pyocr benchmark ./scans/ --concurrency 16   # end-to-end pages/s
curl -F file=@photo.heic "localhost:8010/ocr?figures=true"
```

Engine settings (`OCR__*`): `MODEL`, `BACKEND`, `MAX_TOKENS`, `NUM_SPECULATIVE_TOKENS`,
`GPU_MEMORY_UTILIZATION`, `MAX_NUM_SEQS`, `MAX_MODEL_LEN`, `DEVICE`; `OCR_MAX_SIDE` for render size.

In CIPHER, `cipher ocr` (cipher-orchestration) calls this service; see `docs/enrichments.md`.
