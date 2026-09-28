SHELL=/bin/bash
NAME = cipher-names

install:
	uv sync

test:
	uvx pytest

style:
	uvx ruff check --select I --fix && uvx ruff format
