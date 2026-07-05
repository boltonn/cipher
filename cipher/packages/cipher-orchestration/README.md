# cipher-orchestration

Workflow orchestration for CIPHER: ingesting files into a dataset, and running
analytics (image embedding, face detection, text extraction, text embedding)
against them. The `cipher` CLI is a thin, test-drive-focused wrapper around
these workflows — good for loading a local dataset and seeing what the
pipeline produces.

## Install

```bash
cd cipher
uv sync --extra orchestration --extra postgres --extra elasticsearch
```

This pulls in the CLI plus the analytic packages it can invoke (`filetyper`,
`setfitcv`, `face`, `pyxberg`, `pyparse[email]`, `clir`). Postgres connection
settings come from `.env` at the repo root (`POSTGRES__HOST`,
`POSTGRES__DATABASE`, `POSTGRES__USERNAME`, `POSTGRES__PASSWORD`,
`POSTGRES__PORT`); Elasticsearch settings likewise (`ELASTICSEARCH__HOST`,
`ELASTICSEARCH__PORT`, `ELASTICSEARCH__USERNAME`, `ELASTICSEARCH__PASSWORD`) —
run CLI commands from `cipher/` so `.env` is picked up. Elasticsearch is only
needed for `embed-text`; everything else only needs Postgres.

## Quickstart: load a test dataset and run the pipeline

```bash
# One-time (or after a schema change): create all tables. Safe to re-run.
uv run cipher create-tables

# Create a dataset -- load-files/embed-*/extract-text/etc. all resolve
# --dataset-name to an existing dataset and error if it isn't found yet,
# so this has to run first (once).
uv run cipher create-dataset --name my-test-dataset

# Ingest a directory of files into a dataset. Re-running on the same path
# is a no-op for files already loaded (upsert on dataset + uri).
uv run cipher load-files ~/data/test-photos --dataset-name my-test-dataset

# Run image embedding and face detection — in whichever order you want,
# any number of times. Neither depends on the other having run first.
uv run cipher embed-images --dataset-name my-test-dataset --model-dir "$IMAGE_EMBEDDING_MODEL_DIR"
uv run cipher detect-faces --dataset-name my-test-dataset --model-dir "$FACE_MODEL_DIR"

# Text pipeline: extract, then embed (order matters here -- see below).
# --model-dir on extract-text is only used when --chunker kreuzberg is passed.
uv run cipher extract-text --dataset-name my-test-dataset
uv run cipher embed-text --dataset-name my-test-dataset --model-dir "$TEXT_EMBEDDING_MODEL_DIR"

# See what happened
uv run cipher stats --dataset-name my-test-dataset
```

Add `--limit N` to `load-files` to try a small slice first. Add `--device cuda`
to `embed-images`/`detect-faces`/`embed-text` if you have a GPU.

## The text pipeline: extract-text then embed-text

Unlike images/faces, the text pipeline is two stages that **do** have a
required order, because the second stage reads what the first one wrote
rather than reparsing files:

1. **`extract-text`** — parses eligible files (emails via pyparse, documents
   via xberg) and writes one canonical `ExtractedText` row per file to
   Postgres. Internally this itself runs in a fixed order: **emails before
   documents**. Parsing an email is also how its attachments get discovered
   and written to the `file` table (linked via `parent_id`) — running
   documents first would miss any attachments not yet known about. Both
   sub-steps run automatically, in the right order, from one `extract-text`
   invocation, so you don't need to think about this normally.
2. **`embed-text`** — reads the `ExtractedText` rows `extract-text` wrote,
   chunks them (skipped if `extract-text` already produced chunks via
   `--chunker kreuzberg`) and embeds each chunk into the unified
   `text_chunks` Elasticsearch index (documents and emails share one index,
   discriminated by `content_type`, so "search everything" is a single
   query).

If you run `embed-text` before `extract-text` has finished, or run
`extract-text`'s document step while emails are still pending, you don't get
wrong results — both workflows are idempotent and safe to re-run — but you
may get *incomplete* ones (files/attachments that show up on the next run
instead of this one). Both commands check for this and log a warning if they
detect the dataset is in that state, e.g.:

```
WARNING: This dataset has emails not yet extracted -- running extract_documents_workflow now may miss
attachments discovered by extract_emails_workflow. Consider running emails first (or again after).
```

**`--chunk-size` must match between the two commands.** `extract-text
--chunker kreuzberg` (xberg's own chunker) and `embed-text` (CLIR's chunker,
used whenever `extract-text` didn't already produce chunks) both take a
`--chunk-size` in tokens — keep them equal, or chunk boundaries will differ
depending on which chunker happened to produce them for otherwise-similar
documents. Both default to the same value (`DEFAULT_CHUNK_SIZE` in
`extract_documents.py`) if you don't pass either.

## Idempotency and dedup

Every command here is safe to run more than once, with one exception:

- **`create-dataset` is not** — `name` is unique, so running it twice with
  the same `--name` errors instead of silently reusing the existing dataset.
  It's a one-time setup step, not something you re-run per ingest.
- **`load-files`** upserts on `(dataset, uri)` — loading the same directory
  twice doesn't create duplicate `File` rows.
- **`embed-images`** and **`detect-faces`** each dedupe by content hash
  (sha256) before doing any real work: if the exact same photo already has
  an embedding or detected faces anywhere (any file, any dataset), the
  result is copied instead of recomputed. A duplicate photo loaded 10 times
  only ever gets embedded/detected once. Both can run in **either order** —
  `detect-faces` doesn't need `embed-images` to have run.
- **`extract-text`** and **`embed-text`** are each idempotent per file
  (re-running upserts the same `ExtractedText` row / re-indexes the same
  chunks, deleting a file's prior chunks before re-indexing it), but **do**
  have a required order relative to each other -- see above.

## Other useful commands

```bash
# Check on a dataset without touching it
uv run cipher stats --dataset-name my-test-dataset

# All commands also accept --dataset-id instead of --dataset-name
uv run cipher detect-faces --dataset-id <uuid> --model-dir "$FACE_MODEL_DIR"

# Extract only, without chunking documents yet (embed-text's CLIR chunker will handle it)
uv run cipher extract-text --dataset-name my-test-dataset

# Extract with xberg's own chunker instead of CLIR's (same --chunk-size either way)
uv run cipher extract-text --dataset-name my-test-dataset --chunker kreuzberg --chunk-size 512 --model-dir "$TEXT_EMBEDDING_MODEL_DIR"
uv run cipher embed-text --dataset-name my-test-dataset --chunk-size 512 --model-dir "$TEXT_EMBEDDING_MODEL_DIR"
```

## Benchmarks

Two scripts exist to answer "is this fast enough" with real numbers instead
of guesses -- useful now, and as a baseline if another extractor (e.g.
unstructured.io) is ever swapped in for comparison:

```bash
# Per-file xberg extraction time over a directory (analytics/pyxberg)
uv run pyxberg benchmark ~/data/test-photos --report bench.json

# Postgres upsert/read latency + on-disk size for cached extracted text
uv run cipher benchmark-storage --n 100
```

**`benchmark-storage`'s numbers, measured on this repo's dev Postgres** (100
rows, ~35KB extracted text + 2 tables each, matching a ~10-page OCR'd PDF):
upsert **~6.8ms mean** (p95 ~9ms), read-back **~1.1ms mean**, on-disk size
**~46KB/row** (~4.6GB per 100k documents). Compared against `pyxberg
benchmark`'s own per-file extraction time on this repo's sample PDFs
(**~31ms mean**, up to ~78ms with OCR-heavy pages) — the Postgres write is
roughly 5-10x *faster* than the extraction that produced it. **Caching
extracted text in Postgres is not the bottleneck; extraction (parsing/OCR)
is** — re-verify with `--n`/`--content-chars` if your documents run
significantly larger than ~35KB of text each.
