SHELL=/bin/bash
APP_NAME = cipher
USERNAME ?= boltonn
VERSION ?= $(shell cat config/version.txt)
TODAY ?= $(shell date +%Y-%m-%d)
WORKING_DIR = $(shell pwd)
PORT ?= 8000
_BUILD_NAME = ${APP_NAME}
_BUILD_DOCKERFILE ?= docker/Dockerfile

install-cpu:
	uv sync --group dev --extra analytics-cpu --extra backend

install-cuda:
	UV_INDEX_PYTORCH_CUDA=https://download.pytorch.org/whl/cu126 \
	uv sync --group dev --extra all-cuda --extra backend

start:
	JE_ARROW_MALLOC_CONF=background_thread:false uv run --no-sync cipher-serve
	
test:
	uvx pytest

style:
	uvx ruff check --select I --fix && uvx ruff format

start-setfitcv:
	cd services/analytics/setfitcv && uv run --extra fastapi --extra cuda setfitcv-api