SHELL=/bin/bash
NAME = pyxberg
USERNAME ?= nazgul44
VERSION ?= $(shell grep -E '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
WORKING_DIR = $(shell pwd)
PORT ?= 8000
DEPS_DIR = deps
DEVICE?=cuda


install:
	uv sync

start:
	uv run --no-sync ${NAME}-api
	
test:
	uvx pytest

style:
	uvx ruff check --select I --fix && uvx ruff format