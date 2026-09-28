SHELL=/bin/bash
NAME = pyocr
VERSION ?= $(shell grep -E '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
PORT ?= 8010
MODEL ?= jinaai/jina-ocr-v1
VLLM_VENV = .venv-vllm
LIBS = ../../libs


download-deps:
	hf download $(MODEL)

# Workspace env: transformers fallback + page triage/client (shares the monorepo lock).
install:
	uv sync --extra transformers --extra fastapi

# vLLM pins its own torch, so the fast path lives in a separate venv, outside uv.lock.
# PyPI's vllm wheel targets CUDA 13; CUDA 12.x drivers need the +cu129 build and cu129 torch.
VLLM_VERSION ?= 0.30.0
VLLM_CUDA ?= cu129
install-vllm:
	uv venv --python 3.12 $(VLLM_VENV)
	VIRTUAL_ENV=$(VLLM_VENV) uv pip install --torch-backend=$(VLLM_CUDA) \
		"vllm @ https://github.com/vllm-project/vllm/releases/download/v$(VLLM_VERSION)/vllm-$(VLLM_VERSION)+$(VLLM_CUDA)-cp38-abi3-manylinux_2_28_x86_64.whl" \
		-e $(LIBS)/cipher-schemas -e "$(LIBS)/cipher-utils[fastapi]" -e .
	VIRTUAL_ENV=$(VLLM_VENV) uv pip install --reinstall-package torch --reinstall-package torchvision --reinstall-package torchcodec \
		torch==$$($(VLLM_VENV)/bin/python -c "import torch; print(torch.__version__.split('+')[0])") torchvision torchcodec \
		--index-url https://download.pytorch.org/whl/$(VLLM_CUDA)

start:
	PORT=$(PORT) OCR__MODEL=$(MODEL) OCR__BACKEND=transformers uv run --no-sync $(NAME)-api

start-vllm:
	PORT=$(PORT) OCR__MODEL=$(MODEL) OCR__BACKEND=vllm $(VLLM_VENV)/bin/$(NAME)-api

test:
	uvx pytest

style:
	uvx ruff check --select I --fix && uvx ruff format
