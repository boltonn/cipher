# pyocr

Page OCR for PDFs and images, with two engines behind one interface (`model`, `health`,
`ocr(path, OcrRequest) -> OcrResponse`, `aclose`). `cipher ocr --engine jina|indra` picks one.

| Engine | Class | Runs | Model |
|---|---|---|---|
| `jina` (default) | `pyocr.jina.JinaOcr` | GPU, on pyvllm's local `ocr` server (vLLM, :8010) | jina-ocr-v1 (CC BY-NC 4.0) |
| `indra` | `pyocr.indra.IndraOcr` | CPU, in this process (worker pool), no server | Indra OCR, Datalab (weights: modified OpenRAIL-M) |

Shared by both: `pages` picks the image-based PDF pages (text layer under 20 word characters)
and renders pages (pdfium / Pillow + pillow-heif); `parse` turns page markdown into text,
tables (`ExtractedTableInfo`) and figure regions, and cuts decoding loops (`OcrPage.is_truncated`).

**Why jina goes through a server.** jina-ocr-v1 is a generative vision-language model. In
transformers it reads one page per `generate()` call without its speculative (FastMTP) heads:
0.06 pages/s measured on a 3090, against ~2-5.6 pages/s on vLLM. vLLM pins its own torch, so it
lives in `analytics/pyvllm/.venv-vllm`, and `cipher ocr` starts and stops that server for a run.
Indra is a small ONNX line recogniser, so in-process CPU is its fast path (~5.5 pages/s with 8
workers here).

## Setup

```bash
uv sync --extra indra        # or cipher-orchestration's `ocr` extra, which includes it
make download-indra          # Indra weights; or set INDRA_OCR_MODEL_DIR to a local copy
# jina: `make install && make download` in analytics/pyvllm
```

When to use which engine: `docs/running-analytics.md` → "Choosing an OCR engine".
