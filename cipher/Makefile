SHELL=/bin/bash
APP_NAME = cipher
USERNAME ?= boltonn
VERSION ?= $(shell grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
WORKING_DIR = $(shell pwd)

install-cpu:
	uv sync --group dev --extra analytics-cpu --extra backend

install-cuda:
	UV_INDEX_PYTORCH_CUDA=https://download.pytorch.org/whl/cu126 \
	uv sync --group dev --extra all-cuda --extra backend

start:
	uv run --no-sync cipher-serve
	
test:
	uv run --no-sync pytest

style:
	uvx ruff check --select I --fix && uvx ruff format

lint:
	uv run --no-sync ruff check .

typecheck:
	uv run --no-sync ty check

start-setfitcv:
	cd analytics/setfitcv && uv run --extra fastapi setfitcv-api