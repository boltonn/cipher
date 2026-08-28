SHELL=/bin/bash
NAME = setfitcv
USERNAME ?= nazgul44
VERSION ?= $(shell grep -E '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
WORKING_DIR = $(shell pwd)
PORT ?= 8000
DEPS_DIR = deps
MODEL_GROUP = jhu-clsp
MODEL_NAME = mmBERT-small
DEVICE?=cuda


download-deps:
	@mkdir -p $(DEPS_DIR)/$(MODEL_NAME)
	@if ! hf auth whoami > /dev/null 2>&1; then \
		hf auth login; \
	fi
	hf auth download $(MODEL_GROUP)/$(MODEL_NAME) --local-dir $(DEPS_DIR)/$(MODEL_NAME); \
	cd $(DEPS_DIR)/$(MODEL_NAME); \
	rm -f pytorch_model.bin; \
	wget -P ${DEPS_DIR}/${MODEL_NAME} https://huggingface.co/jhu-clsp/mmBERT-small/resolve/refs%2Fpr%2F7/model.safetensors?download=true -O model.safetensors;


copy-deps-to-s3: check-env
	# Copy model to S3
	aws s3 cp ${DEPS_DIR}/${MODEL_NAME} ${S3_MODEL_PATH} --recursive

get-deps-from-s3: check-env
	# Copy model from S3
	if [ ! -d "${DEPS_DIR}/${MODEL_NAME}" ]; then \
		aws s3 cp ${S3_MODEL_PATH} ${DEPS_DIR}/${MODEL_NAME} --recursive; \
	fi

install:
	uv sync --extra dev --extra ${DEVICE} --extra fastapi --extra cli

start:
	uv run --no-sync ${NAME}-api
	
test:
	uvx pytest

style:
	uvx ruff check --select I --fix && uvx ruff format
