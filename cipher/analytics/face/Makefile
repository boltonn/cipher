SHELL=/bin/bash
NAME = face
USERNAME ?= nazgul44
VERSION ?= $(shell grep -E '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
WORKING_DIR = $(shell pwd)
PORT ?= 8000
DEPS_DIR = deps
DEVICE?=cuda


download-deps:
	@echo "Not implemented yet. Please download the models manually from InsightFace and place them in the deps directory."

install:
	uv sync --extra dev --extra ${DEVICE} --extra cli --extra fastapi --extra eval

start:
	uv run --no-sync ${NAME}-api
	
test:
	uvx pytest

style:
	uvx ruff check --select I --fix && uvx ruff format
