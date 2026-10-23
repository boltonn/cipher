SHELL=/bin/bash

# Indra OCR weights (~76 MB): the model tag indra-ocr was built against, into the HF cache.
# jina-ocr-v1 is downloaded and served by analytics/pyvllm (`make download`).
download-indra:
	uv run --no-sync python -c "import indra_ocr; print(indra_ocr.model_dir())"

test:
	uv run --no-sync pytest tests

style:
	uvx ruff check --select I --fix && uvx ruff format
