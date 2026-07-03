# cipher-orchestration

Workflow orchestration for CIPHER: ingesting files into a dataset, and running
analytics (image embedding, face detection) against them. The `cipher-orchestrate`
CLI is a thin, test-drive-focused wrapper around these workflows — good for
loading a local dataset and seeing what the pipeline produces.

## Install

```bash
cd cipher
uv sync --extra orchestration --extra postgres
```

This pulls in the CLI plus the analytic packages it can invoke (`filetyper`,
`setfitcv`, `face`). Postgres connection settings come from `.env` at the repo
root (`POSTGRES__HOST`, `POSTGRES__DATABASE`, `POSTGRES__USERNAME`,
`POSTGRES__PASSWORD`, `POSTGRES__PORT`) — run CLI commands from `cipher/` so
that file is picked up.

## Quickstart: load a test dataset and run the pipeline

```bash
# One-time (or after a schema change): create all tables. Safe to re-run.
uv run cipher-orchestrate create-tables

# Ingest a directory of files into a dataset. Re-running on the same path
# is a no-op for files already loaded (upsert on dataset + uri).
uv run cipher-orchestrate load-images ~/data/test-photos --dataset-name my-test-dataset

# Run image embedding and face detection — in whichever order you want,
# any number of times. Neither depends on the other having run first.
uv run cipher-orchestrate embed-images --dataset-name my-test-dataset --model-dir "$IMAGE_EMBEDDING_MODEL_DIR"
uv run cipher-orchestrate detect-faces --dataset-name my-test-dataset --model-dir "$FACE_MODEL_DIR"

# See what happened
uv run cipher-orchestrate stats --dataset-name my-test-dataset
```

Add `--limit N` to `load-images` to try a small slice first. Add `--device cuda`
to `embed-images`/`detect-faces` if you have a GPU.

## Idempotency and dedup

Every command here is safe to run more than once, and safe to run out of order:

- **`load-images`** upserts on `(dataset, uri)` — loading the same directory
  twice doesn't create duplicate `File` rows.
- **`embed-images`** and **`detect-faces`** each dedupe by content hash
  (sha256) before doing any real work: if the exact same photo already has
  an embedding or detected faces anywhere (any file, any dataset), the
  result is copied instead of recomputed. A duplicate photo loaded 10 times
  only ever gets embedded/detected once.
- Both can run in **either order**. `detect-faces` doesn't need
  `embed-images` to have run — it creates a bare image-metadata row
  (width/height only) on demand and never touches an existing embedding.

## Other useful commands

```bash
# Check on a dataset without touching it
uv run cipher-orchestrate stats --dataset-name my-test-dataset

# All commands also accept --dataset-id instead of --dataset-name
uv run cipher-orchestrate detect-faces --dataset-id <uuid> --model-dir "$FACE_MODEL_DIR"
```
