FROM continuumio/miniconda3

RUN groupadd -r pyparse && useradd --no-log-init -r -g pyparse pyparse

COPY ./ /app
RUN chown -R pyparse:pyparse /app/*
RUN chmod -R 755 /app/*
WORKDIR /app/
RUN ls -lah /app/*

RUN conda config --add channels conda-forge
RUN conda install mamba
RUN mamba env update -n base -f environment.yml \
    && conda clean -afy \
    && find . -type f -name '*.py[co]' -delete -o -type d -name __pycache__ -delete
RUN python -m pip install --no-cache-dir -e .[api]
# SHELL ["conda", "run", "-n", "pyparse", "/bin/bash", "-c"]

EXPOSE 8080
CMD uvicorn pyparse.api:app --host 0.0.0.0 --port 8080
# ENTRYPOINT conda run -n pyparse --no-capture-output python src/pyparse/api.py --host 0.0.0.0 --port 80