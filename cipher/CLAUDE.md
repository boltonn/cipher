# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (CPU-only)
make install-cpu

# Install (CUDA/GPU)
make install-cuda

# Run backend API (http://localhost:8000)
make start

# Run tests
make test

# Format and lint
make style

# Run image embedding service
make start-setfitcv
```

Run a single test file: `uvx pytest backend/tests/test_chat.py`

Every `cipher` command is listed in `docs/cli.md` (pipeline order: `docs/running-analytics.md`). Add a
command only if it will be re-run (a pipeline step or a maintenance tool such as `cipher rekey`);
a one-time repair is a migration or a throwaway script. Update `docs/cli.md` when adding or removing one.

## Architecture

This is a UV workspace monorepo for a AI/ML based data triage platform.

### Workspace layout

```bash
analytics/     # ML analytics services (each independently deployable)
  clir/        # Multilingual text embedding (Jina model)
  face/        # Face Recognition using InsightFace
  filetyper/   # File type detection (Google Magika + heuristics)
  pykreuzberg/ # Rust-based text extraction & OCR
  pyparse/     # Email/document parsing (.eml, .msg, VCF, DOCX, PDF, etc.)
  setfitcv/    # Image embedding via CLIP
  pyocr/       # Page OCR: jina-ocr-v1 (GPU, via pyvllm's server) or Indra OCR (CPU, in-process)
  pyvllm/      # Local models on one vLLM install (LLM: Qwen3.8-27B; OCR: jina-ocr-v1)
backend/       # FastAPI REST API (entry: cipher-serve)
packages/
  cipher-orchestration # Combining analytics applied to data ingestion into a datastore with CLI utilities
  cipher-datastores/  # DB layer: PostgreSQL (pgvector) + Elasticsearch
  cipher-schemas/     # Pydantic v2 models shared across all services
  cipher-utils/       # FastAPI, AWS, or other general utilities applicable to backend or multiple services
```

### Shared packages

- **cipher-schemas** — source of truth for all Pydantic models (User, Dataset, File, Image, Message, Email, Enrichment, Job) and exception types (`EntityNotFoundError`, `EntityAlreadyExistsError`)
- **cipher-datastores** — `AsyncEngine`/`AsyncSession` setup, base repository classes with Postgres and Elasticsearch implementations
- **cipher-utils** — settings base class, FastAPI middleware (structured logging, CORS, exception handlers)

### Terminology

`docs/glossary.md` is the canonical vocabulary — one term, one meaning across schemas, tables, API, CLI, frontend, and docs. Use those words exactly (e.g. `filetype_group`, not "content type"); backend `snake_case` ↔ frontend `camelCase` is the only permitted variation. Add a term there the first time it needs defending.
