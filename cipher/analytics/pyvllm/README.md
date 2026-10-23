# pyvllm

Every local model on one vLLM install. Each model is its own `vllm serve` process with an
OpenAI-compatible API on localhost; this analytic installs vLLM once and starts and stops the models.

| Model | Handle | Port | GPU | Used by |
|---|---|---|---|---|
| Qwen3.8-27B, 4-bit (`RedHatAI/Qwen3.8-27B-INT4`, Apache-2.0) | `llm` | 8008 | 1 | chat, pyprompt, `extract-llm` |
| jina-ocr-v1 (CC BY-NC 4.0: non-commercial without a Jina AI agreement) | `ocr` | 8010 | 0 | `cipher ocr --engine jina` via `analytics/pyocr` (started and stopped by the job) |

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

The OCR side (page rendering, the jina-ocr-v1 client, Indra OCR on CPU, output parsing) is its
own analytic, `analytics/pyocr`. This analytic only serves the `ocr` model it talks to.
