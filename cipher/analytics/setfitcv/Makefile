SHELL=/bin/bash
NAME = setfitcv
USERNAME ?= nazgul44
VERSION ?= $(shell grep -E '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
WORKING_DIR = $(shell pwd)
PORT ?= 8000
_BUILD_DOCKERFILE ?= docker/Dockerfile
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

build: get-deps-from-s3
	docker build -t ${ECR_ADDRESS}/${USERNAME}/${NAME}:${VERSION} -f ${_BUILD_DOCKERFILE} --platform linux/x86_64 . \
		--build-arg ECR_ADDRESS=${ECR_ADDRESS} \
		--build-arg DEPS_DIR=${DEPS_DIR} \
		--build-arg MODEL_NAME=${MODEL_NAME} \
		--build-arg ENVIRONMENT_BUILD=${DEVICE}
	
run:
	if [ "${DEVICE}" = "cuda" ]; then \
		docker run -p ${PORT}:${PORT} -it --rm --gpus all --platform linux/x86_64 ${ECR_ADDRESS}/${USERNAME}/${NAME}:${VERSION}; \
	else \
		docker run -p ${PORT}:${PORT} -it --rm --platform linux/x86_64 ${ECR_ADDRESS}/${USERNAME}/${NAME}:${VERSION}; \
	fi

run-bash:
	if [ "${DEVICE}" = "cuda" ]; then \
		docker run -p ${PORT}:${PORT} -it --rm --gpus all --platform linux/x86_64 --entrypoint /bin/bash ${ECR_ADDRESS}/${USERNAME}/${NAME}:${VERSION}; \
	else \
		docker run -p ${PORT}:${PORT} -it --rm --platform linux/x86_64 --entrypoint /bin/bash ${ECR_ADDRESS}/${USERNAME}/${NAME}:${VERSION}; \
	fi
    
push:
	docker push ${ECR_ADDRESS}/${USERNAME}/${NAME}:${VERSION}
    
release:
	docker pull ${ECR_ADDRESS}/${USERNAME}/${NAME}:${VERSION}
	docker tag  ${ECR_ADDRESS}/${USERNAME}/${NAME}:${VERSION} ${ECR_ADDRESS}/${USERNAME}/${NAME}:latest
	docker push ${ECR_ADDRESS}/${USERNAME}/${NAME}:latest
