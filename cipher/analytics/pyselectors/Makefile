SHELL=/bin/bash
NAME = pyselectors
VERSION ?= $(shell grep -E '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
PORT ?= 8000


install:
	uv sync --extra fastapi

start:
	uv run --no-sync ${NAME}-api

test:
	uvx pytest

style:
	uvx ruff check --select I --fix && uvx ruff format
