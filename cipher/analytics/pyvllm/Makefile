SHELL=/bin/bash
NAME = pyvllm
VLLM_VENV = .venv-vllm
VLLM_VERSION ?= 0.30.0
VLLM_CUDA ?= cu129
LLM_MODEL ?= RedHatAI/Qwen3.8-27B-INT4
OCR_MODEL ?= jinaai/jina-ocr-v1

# vLLM pins its own torch, so it lives in this analytic's own venv, outside uv.lock.
# PyPI's vllm wheel targets CUDA 13; CUDA 12.x drivers need the +cu129 build and cu129 torch.
install:
	uv venv --allow-existing --python 3.12 $(VLLM_VENV)
	VIRTUAL_ENV=$(VLLM_VENV) uv pip install --torch-backend=$(VLLM_CUDA) \
		"vllm @ https://github.com/vllm-project/vllm/releases/download/v$(VLLM_VERSION)/vllm-$(VLLM_VERSION)+$(VLLM_CUDA)-cp38-abi3-manylinux_2_28_x86_64.whl" \
		-e .
	VIRTUAL_ENV=$(VLLM_VENV) uv pip install --reinstall-package torch --reinstall-package torchvision --reinstall-package torchcodec \
		torch==$$($(VLLM_VENV)/bin/python -c "import torch; print(torch.__version__.split('+')[0])") torchvision torchcodec \
		--index-url https://download.pytorch.org/whl/$(VLLM_CUDA)

download:
	$(VLLM_VENV)/bin/hf download $(LLM_MODEL) --local-dir $(HOME)/models/$(LLM_MODEL)
	$(VLLM_VENV)/bin/hf download $(OCR_MODEL)

up:
	$(VLLM_VENV)/bin/$(NAME) up $(MODELS)

down:
	$(VLLM_VENV)/bin/$(NAME) down $(MODELS)

status:
	$(VLLM_VENV)/bin/$(NAME) status

style:
	uvx ruff check --select I --fix && uvx ruff format
