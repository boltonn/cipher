SHELL=/bin/bash
CONDA_ACTIVATE = source $$(conda info --base)/etc/profile.d/conda.sh ; conda activate ; conda activate
NAME = pyparse

install:
	mamba env create -f environment.yml || mamba env update -f environment.yml
	$(CONDA_ACTIVATE) $(NAME)

start:
	$(CONDA_ACTIVATE) $(NAME)
	conda run --no-capture-output --name $(NAME) api

test:
	$(CONDA_ACTIVATE) $(NAME)
	pytest -W ignore::DeprecationWarning

style:
	$(CONDA_ACTIVATE) $(NAME)
	black --line-length=140 .
	flake8 --max-line-length=140 . --per-file-ignores="__init__.py:F401"
	isort .

