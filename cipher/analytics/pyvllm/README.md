# pyvllm

Every local model on one vLLM install. Each model is its own `vllm serve` process with an
OpenAI-compatible API; this analytic installs vLLM once, starts and stops the models, and
holds the OCR client.

| Model | Handle | Port | GPU | Used by |
|---|---|---|---|---|
| Qwen3.8-27B, 4-bit (`RedHatAI/Qwen3.8-27B-INT4`, Apache-2.0) | `llm` | 8008 | 1 | chat, pyprompt, `extract-llm` |
| jina-ocr-v1 (CC BY-NC 4.0: non-commercial without a Jina AI agreement) | `ocr` | 8010 | 0 | `cipher ocr` (started and stopped by the job) |

Specs live in `src/pyvllm/models.py`. jina-ocr-v1 brings its own architecture code inside
the model snapshot; the `vllm.general_plugins` entry point (`pyvllm.plugins`) registers it,
so it serves like any other model.

## Run

```bash
make install        # .venv-vllm with vLLM 0.30 (cu129) + this package
make download       # both models
make up             # or: .venv-vllm/bin/pyvllm up llm
make status
make down MODELS=llm
```

Set `VLLM_API_KEY` to require a key (vLLM reads it; the OCR client sends it).

## OCR

`pyvllm.ocr` is the client side of page OCR: `pages` decides which PDF pages are
image-based (text layer under 20 word characters) and renders them (pdfium / Pillow +
pillow-heif, longest side 1600 px); `client.OcrClient` sends every page of every in-flight
file to the `ocr` server at once; `parse` turns the markdown into page text, tables and
figure regions, and cuts decoding loops (`OcrPage.is_truncated`).
