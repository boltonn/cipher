SHELL=/bin/bash
NAME = nerd
VERSION ?= $(shell grep -E '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
PORT ?= 8000
DEVICE ?= cpu


install:
	uv sync --extra fastapi --extra ${DEVICE}

install-train:
	uv sync --extra fastapi --extra ${DEVICE} --extra train

start:
	uv run --no-sync ${NAME}-api

test:
	uvx pytest

style:
	uvx ruff check --select I --fix && uvx ruff format
