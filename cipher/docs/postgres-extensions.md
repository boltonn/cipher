# Postgres extensions

Everything the database needs, why, and how to install it. Retrieval design:
`docs/retrieval-architecture.md`.

## Which image you're on

- **`paradedb/paradedb` (the current dev/compose image, Debian, PG 18)** — ships
  **`pg_search`** (BM25 / Tantivy) built in, plus `vector`, `pg_trgm`,
  `postgis`, `unaccent`. It does **not** carry `pg_bigm` or `pgroonga`. Set
  `RETRIEVAL__TEXT_RANKER=pg_search` and you get real multilingual ranking with
  zero extra install — this is the recommended default here.
- **A plain PGDG image on Rocky Linux 9 / PG 16** — the offline `pg_bigm` /
  `pgroonga` RPM steps further down apply.

The backend attempts `CREATE EXTENSION` for **only the extension its configured
`RETRIEVAL__TEXT_RANKER` needs** (`bigm`→`pg_bigm`, `pgroonga`→`pgroonga`,
`pg_search`→`pg_search`, `core`→none), in a savepoint, and downgrades one rung
(`_effective_ranker`) if that package is absent. So a mismatched ranker logs one
warning and keeps working; a matched ranker (or `core`) is silent.

## The list

| Extension | Status | Used for | Package |
|---|---|---|---|
| **`vector`** (pgvector) | required, already installed | `chunk.embedding` / image / face / entity-name kNN (HNSW) | `pgvector_16` (PGDG) — already in the image |
| **`pg_trgm`** | required, already installed | trigram fuzzy match on entity names; Latin substring/typo matching | ships with `postgresql16-contrib` |
| **`postgis`** | required, already installed | the `location` table (geospatial) | `postgis34_16` (PGDG) |
| **`unaccent`** | **required, new** | diacritic folding in the full-text vector (`unaccent(text)`) so `café` matches `cafe` | ships with `postgresql16-contrib` — **no separate download**, just `CREATE EXTENSION` |
| **`pg_bigm`** | **recommended, new** | bigram index on `chunk.text` — makes Chinese / Farsi / Ukrainian / unknown-language keyword search actually retrieve (core `tsvector` can't tokenize them) | `pg_bigm_16` (PGDG) — one RPM |
| `pgroonga` | optional upgrade | near-Elasticsearch multilingual ranking (proper CJK/Japanese/Korean tokenizers) | `pgroonga` (Groonga repo) |
| `pg_search` | optional upgrade | real BM25 (ParadeDB, Tantivy) | ParadeDB RPM |

**On the ParadeDB image nothing needs adding — use `RETRIEVAL__TEXT_RANKER=pg_search`.**
On a plain PGDG image you add `pg_bigm` (one RPM) for the `bigm` ranker.

`unaccent`, `pg_trgm`, `postgis`, and `vector` are created automatically at
startup (`init_db` / `init_db_from_settings`). The ranker's own extension is
*attempted* there too and, if its package isn't installed, logged once and the
retrieval layer downgrades a rung. Nothing errors. `cipher create-tables` does the
same for `pg_search` and its BM25 index.

The downgrade is resolved once per process from `pg_extension`
(`effective_text_ranker` in `chunk_retrieval.py`), so every search, the embed
pipeline and `GET /search/config` agree. Below `pg_search`, keyword search reads
`chunk.text_tsv` (`to_tsvector('simple', text)`): chunks write it, and startup
backfills any rows embedded while `pg_search` was in use. On a large corpus,
expect that first startup to take a while.

## Check what's live

```
GET /api/search/config
```

returns the active backend, the configured vs. **effective** keyword ranker, and
the installed full-text extensions:

```json
{
  "backend": "postgres",
  "textRanker": "bigm",
  "textRankerEffective": "core",          // pg_bigm not installed -> downgraded
  "installedExtensions": ["pg_trgm", "unaccent", "vector"],
  "graphExpandEntityCap": 10000
}
```

Or straight from SQL:

```sql
SELECT extname, extversion FROM pg_extension ORDER BY extname;
```

The backend also logs one line at startup:
`retrieval backend: postgres (text_ranker=bigm)`.

## Installing `pg_bigm` offline (Rocky 9, containerised Postgres)

`pg_bigm` is a compiled C extension. On an air-gapped host you stage the RPM in
the repo (or an internal mirror) and install it into the Postgres image.

1. **Get the RPM** matching the Postgres major version and arch, from a machine
   with internet:

   ```
   # PGDG carries it: https://download.postgresql.org/pub/repos/yum/16/redhat/rhel-9-x86_64/
   pg_bigm_16-1.2-XX.rhel9.x86_64.rpm
   ```

2. **Stage it** in the repo:

   ```
   assets/pg_bigm/pg_bigm_16-1.2-XX.rhel9.x86_64.rpm
   ```

   (or `make stage-fts-ext` copying from your mirror — target TBD).

3. **Install into the Postgres image** — Dockerfile fragment, fully offline:

   ```dockerfile
   COPY assets/pg_bigm/*.rpm /tmp/pg_bigm/
   RUN dnf install -y /tmp/pg_bigm/*.rpm && rm -rf /tmp/pg_bigm
   ```

4. **Enable it** — automatic on next backend start (`init_db` runs
   `CREATE EXTENSION IF NOT EXISTS pg_bigm`), or manually:

   ```sql
   CREATE EXTENSION pg_bigm;
   ```

5. **Confirm**: `GET /api/search/config` shows `"pg_bigm"` in
   `installedExtensions` and `textRankerEffective: "bigm"`.

Pin the RPM to the Postgres **minor** line the container runs; a Postgres upgrade
needs a rebuilt/rematched RPM.

## Optional: `pgroonga` (best multilingual ranking without ES)

Same shape. Groonga publishes Rocky 9 RPMs:

```
# from https://packages.groonga.org/almalinux/9/
groonga-release-latest.noarch.rpm      # (or vendor the individual RPMs)
pgroonga_16-*.rpm
```

```dockerfile
COPY assets/pgroonga/*.rpm /tmp/pgroonga/
RUN dnf install -y /tmp/pgroonga/*.rpm && rm -rf /tmp/pgroonga
```

Then set `RETRIEVAL__TEXT_RANKER=pgroonga`. The migration that adds the keyword
index will create a `pgroonga` index instead of the bigram GIN when this ranker
is selected. `pgroonga` brings its own dependency chain (Groonga runtime,
MeCab-style tokenizers) — heavier image, but no query-side code differences.

## Optional: `pg_search` (ParadeDB BM25)

Heaviest option; `pgrx`-compiled. ParadeDB publishes EL9 RPMs. Set
`RETRIEVAL__TEXT_RANKER=pg_search`. Only worth it if `pgroonga` ranking proves
insufficient for a specific corpus.

## Configuration

`RETRIEVAL__*` env vars (nested delimiter `__`), read into `Settings.retrieval`:

| Var | Values | Default | Meaning |
|---|---|---|---|
| `RETRIEVAL__BACKEND` | `postgres`, `elasticsearch` | `postgres` | which store answers chunk search |
| `RETRIEVAL__TEXT_RANKER` | `core`, `bigm`, `pgroonga`, `pg_search` | `pg_search` | keyword ranker (postgres backend only) |
| `RETRIEVAL__GRAPH_EXPAND_ENTITY_CAP` | int | `10000` | graph-RAG fan-out ceiling |

Setting a ranker whose extension isn't installed is safe — it silently
downgrades (see `textRankerEffective`).
