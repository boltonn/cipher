SHELL=/bin/bash
NAME = filetyper
USERNAME ?= nazgul44
VERSION ?= $(shell grep -E '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
WORKING_DIR = $(shell pwd)
PORT ?= 8000
_BUILD_DOCKERFILE ?= docker/Dockerfile
DEPS_DIR = deps
DEVICE?=cuda


install:
	uv sync --extra fastapi

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
