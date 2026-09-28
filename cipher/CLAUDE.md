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

## Architecture

This is a UV workspace monorepo for a AI/ML based data triage platform.

### Workspace layout

```bash
analytics/     # ML analytics services (each independently deployable)
  clir/        # Multilingual text embedding (Jina model)
  face/        # Face Recognition using InsightFace
  filetyper/   # File type detection (Google Magika + heuristics)
  pykreuzberg/ # Rust-based text extraction & OCR
  pyocr/       # Multilingual page OCR (jina-ocr-v1 on vLLM) for image-based PDF pages + images
  pyparse/     # Email/document parsing (.eml, .msg, VCF, DOCX, PDF, etc.)
  setfitcv/    # Image embedding via CLIP
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
