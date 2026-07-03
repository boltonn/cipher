SHELL=/bin/bash
NAME = clir
USERNAME ?= nazgul44
VERSION ?= $(shell grep -E '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
WORKING_DIR = $(shell pwd)
PORT ?= 8000
_BUILD_DOCKERFILE ?= docker/Dockerfile
DEPS_DIR = deps
MODEL_GROUP = jinaai
MODEL_NAME = jina-embeddings-v5-text-small
# MODEL_GROUP = intfloat
# MODEL_NAME = multilingual-e5-large
DEVICE?=cuda


download-deps:
	@mkdir -p $(DEPS_DIR)/$(MODEL_NAME)
	@if ! hf auth whoami > /dev/null 2>&1; then \
		hf auth login; \
	fi
	hf download $(MODEL_GROUP)/$(MODEL_NAME) --local-dir $(DEPS_DIR)/$(MODEL_NAME);

copy-deps-to-s3: check-env
	# Copy model to S3
	aws s3 cp ${DEPS_DIR}/${MODEL_NAME} ${S3_MODEL_PATH} --recursive

get-deps-from-s3: check-env
	# Copy model from S3
	if [ ! -d "${DEPS_DIR}/${MODEL_NAME}" ]; then \
		aws s3 cp ${S3_MODEL_PATH} ${DEPS_DIR}/${MODEL_NAME} --recursive; \
	fi

install:
	uv sync --extra dev --extra ${DEVICE} --extra cli --extra fastapi --extra eval

start:
	uv run --no-sync ${NAME}-api
	
test:
	uvx pytest

style:
	uvx ruff check --select I --fix && uvx ruff format
