# Retrieval architecture

**Status:** P0–P3 landed for both backends. Supersedes the `sync-chunk-entities`
batch projection ([[project-entity-text-search]]).

**Decision.** Chunk search sits behind one `ChunkRetrievalRepository` ABC with
**two fully-maintained adapters** — Postgres (`chunk` table: text + embedding +
full-text vector) and Elasticsearch (the existing `text_chunks` index, BM25/kNN,
its multilingual analyzers). `RETRIEVAL__BACKEND` picks which one answers traffic;
neither is a fallback. Entity/selector/multi-hop-graph filtering composes with
keyword/semantic search **in the same query either way** — for Postgres that's one
SQL statement (`mention` joined in); for Elasticsearch it's the entity/graph
filter resolved live against Postgres `mention` into a chunk-id list, then one
`terms` filter ANDed into the same ES query. Neither adapter denormalizes entity
data onto the search doc — there's no batch sync step, no staleness window, for
either backend.

This is also the first of what should eventually be an Elasticsearch-equivalent
adapter for every repository that currently only has a Postgres one (the
`base/*.py` ABC + two-adapters pattern generalizes) — search was the one under
active development, so it's the one built first.

Terminology follows `docs/glossary.md` (`filetype_group`, `chunk`, `mention`,
`entity`, `selector_type`/`selector_subtype`, `relationship`). The end-to-end
pipeline in plain language is `docs/retrieval-workflow.md` — read that first if
you're new to this.

---

## 1. Why not what's there

- Chunk search is Elasticsearch (`text_chunks`), a bare concrete repo with **no
  ABC** — unlike `user` / `file` / `dataset` / `graph`.
- Entity-aware search needs entity ids on each chunk doc. Today that's a
  **full-dataset batch** (`sync-chunk-entities`): O(files) ES round-trips,
  O(dataset) memory, stale between an extract run and the next sync. Doesn't
  survive ~1M files.
- Multi-hop graph-RAG ("retrieve for Bob **or anyone Bob emails**") isn't
  expressible — the graph is in Postgres, the text in ES, nothing joins them at
  query time.
- Vector search for images, faces, and entity names is **already** pgvector +
  HNSW in Postgres. The ES chunk index is the outlier.

The `mention` anchors to file text by character offset; a `chunk` carries
`start_offset`/`end_offset` into the same text. `chunk ↔ mention` is a
deterministic range-join that always exists. Put both in one database and it's a
plain foreign key.

## 2. Non-goals

- Replacing `GraphRepository`. Traversal/dossiers/resolution stay there; this
  interface *consumes* it to resolve a graph filter.
- Moving image / face / entity-name vector search. Untouched.
- Message search. Out of scope — messages keep their own repo; whether they
  belong in the same embedding space is undecided. Message *entity resolution* is
  unaffected (it runs off `mention`, not chunk searchability).
- Running two live retrieval stores. Elasticsearch is a *possible* adapter behind
  the ABC, not a maintained one. No steady-state dual write.

## 3. The interface

`cipher/datastores/base/retrieval.py`:

```python
class ChunkRetrievalRepository(ABC):
    """Storage-agnostic chunk retrieval + lifecycle. Postgres is the built adapter."""

    @abstractmethod
    async def search(self, query: RetrievalQuery) -> PaginatedResponse[FileSearchResult]:
        """Rank chunks by `mode`, restricted by every filter, grouped by file."""

    @abstractmethod
    async def upsert_chunks(self, chunks: list[TextChunk]) -> tuple[int, int]:
        """Insert/replace chunk rows for their files. Returns (written, failed)."""

    @abstractmethod
    async def delete_by_file_id(self, file_id: str) -> int: ...

    @abstractmethod
    async def delete_by_dataset_id(self, dataset_id: str) -> int: ...

    @abstractmethod
    async def attach_duplicate(self, *, dataset_id: str, sha256: str, file_id: str) -> bool:
        """Add `file_id` to the `duplicate_file_ids` of the rows for this content."""

    @abstractmethod
    async def spans_for_file(self, file_id: str) -> list[ChunkSpan]:
        """(chunk_id, start_offset, end_offset) for a file's chunks, in order --
        the input to the mention→chunk bisect at extraction time."""
```

No `refresh_entities`: entity/graph filtering is a **live join to `mention`**, so
there is nothing to project or keep fresh.

### `RetrievalQuery` (cipher-schemas `content/search.py`)

One model; the existing `ChunkTextSearchRequest` / `ChunkSemanticSearchRequest` /
`ChunkHybridSearchRequest` become thin constructors over it.

```python
class RetrievalQuery(BaseModel):
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"

    text: str | None = None                 # keyword / hybrid
    embedding: list[float] | None = None    # semantic / hybrid (pre-computed)
    query_language: str | None = None       # picks the FTS config for `text`

    filters: ChunkFilters = ChunkFilters()  # dataset_id, file_id, filetype_group,
                                            # filetype, tags, and the entity fields
                                            # already on ChunkFilters:
                                            #   entity_ids, entity_types,
                                            #   selector_types, selector_subtypes

    graph_expand: GraphExpand | None = None # multi-hop: expand a seed entity, then
                                            # restrict to chunks mentioning any of it

    min_similarity: float | None = None     # semantic / hybrid only
    page: int = 1
    limit: int = 10
    sort_by: ChunkSortField = ChunkSortField.SCORE


class GraphExpand(BaseModel):
    seed_entity_id: str
    max_depth: int = Field(1, ge=1, le=3)
    min_weight: float = 0.0
    relationship_types: list[RelationshipType] | None = None
```

**Composition:**

| Field group | Combined with the rest by | Within the group |
|---|---|---|
| `text` / `embedding` (`mode`) | scoring | — |
| `filters` dataset/file/filetype/tags | AND | `tags` OR |
| `filters.entity_ids` | AND (chunk mentions **all**) | — |
| `filters.entity_types` / `selector_types` / `selector_subtypes` | AND | OR within each |
| `graph_expand` | AND (chunk mentions **some** entity in the expansion) | — |

`text` empty with an entity/graph filter is a valid **browse** — rank by recency,
filter by the graph.

## 4. The `chunk` table (the store)

```
chunk
  id                 text  PK   -- chunk_id_for(dataset_id, sha256, chunk_index, start_offset)
  dataset_id         text  FK -> dataset
  file_id            text  FK -> file      -- representative file
  sha256             text                  -- parent file content hash
  filetype_group     text                  -- 'document' | 'email'
  duplicate_file_ids jsonb                 -- files in this dataset sharing this row (incl. file_id)
  chunk_index        int
  start_offset       int
  end_offset         int
  text               text
  language           text  null            -- best-effort; metadata only, NOT required for search
  embedding          vector(1024)          -- P1
  text_tsv           tsvector  null        -- P1, only for the `core` keyword ranker (see §5)
  date_created       timestamptz
```

The keyword index is built on `text` directly by every ranker except `core`
(`pg_search` / `pgroonga` / `pg_bigm` all tokenize the column themselves). `text_tsv`
exists only for the `core` fallback. `language` is populated when a detector runs
(extract-time or a `lingua` enrichment) but search does **not** depend on it — the
default `pg_search` ICU tokenizer is script-agnostic.

- **Deterministic `id`** — `chunk_id_for(dataset_id, sha256, chunk_index,
  start_offset)` (`cipher.schemas.content.search`; wired into `TextChunk.id`,
  filled on validation when blank). A re-embed with the same chunking reuses ids
  → upsert, not duplicate → `mention.chunk_id` survives. Content-identical files
  in a dataset resolve to the same ids and **share one row** (never processed
  twice); `dataset_id` is in the key because a chunk carries denormalized
  `dataset_id`/`tags`.
- **`mention.chunk_id`** (nullable FK → `chunk.id`, `ON DELETE SET NULL`, partial
  indexes). Set at mention write-time: `extract-selectors` / `extract-entities`
  already hold the file's `ExtractedText`; they call `spans_for_file(file_id)`
  once and bisect each mention's `start_offset` into its chunk. The join is
  **content-keyed** — a mention in any file in `duplicate_file_ids` resolves to
  the shared row, so duplicate files need no rows of their own.
- Landed in P0: everything above except `embedding` / `text_tsv` and their
  indexes (P1). Migration `0019_chunk_table`.

## 5. Postgres adapter

`search()` is **one SQL statement** — schematically:

```sql
WITH expand AS (                              -- only when graph_expand is set
  -- recursive CTE over entity_relationship from :seed_entity_id,
  -- bounded by :max_depth / :min_weight / :relationship_types
  SELECT entity_id FROM ...
),
scored AS (
  SELECT c.id, c.file_id, c.chunk_index, c.text, c.start_offset, c.end_offset,
         CASE :mode
           WHEN 'keyword'  THEN ts_rank_cd(c.text_tsv, :tsquery)
           WHEN 'semantic' THEN 1 - (c.embedding <=> :qvec)
           ELSE /* hybrid: RRF of the two orderings, see §7 */ 0
         END AS score
  FROM chunk c
  WHERE c.dataset_id = :dataset_id
    AND (:filetype_group IS NULL OR c.filetype_group = :filetype_group)
    AND (:file_id        IS NULL OR c.file_id = :file_id
                                 OR c.duplicate_file_ids @> to_jsonb(:file_id::text))
    AND (:tsquery IS NULL OR c.text_tsv @@ :tsquery)                       -- keyword
    AND (:entity_ids IS NULL OR NOT EXISTS (                              -- mentions ALL
          SELECT unnest(:entity_ids::text[])
          EXCEPT SELECT m.entity_id FROM mention m WHERE m.chunk_id = c.id))
    AND (:selector_types IS NULL OR EXISTS (                             -- mentions SOME
          SELECT 1 FROM mention m
          WHERE m.chunk_id = c.id AND m.selector_type = ANY(:selector_types)))
    AND (:graph_expand IS NULL OR EXISTS (
          SELECT 1 FROM mention m
          WHERE m.chunk_id = c.id AND m.entity_id IN (SELECT entity_id FROM expand)))
)
SELECT file_id,
       max(score) AS top_score,
       count(*)   AS match_count,
       (array_agg(id ORDER BY score DESC))[1] AS top_chunk_id,
       json_agg(... ORDER BY chunk_index) FILTER (WHERE ...) AS chunks   -- capped
FROM scored
GROUP BY file_id
ORDER BY top_score DESC
LIMIT :limit OFFSET :offset;
```

Grouping-by-file and the pagination contract (`total` = true distinct-file count;
a page is exactly `limit` files) match the current ES behaviour so `FileSearchResult`
and every caller are unchanged.

### Multilingual full-text

The corpus is per-document mostly one language (ru / uk / en / zh, or an es+en
mix), not polyglot within a document. The right tool is **one script-agnostic
tokenizer for the whole `text` column** — the Postgres equivalent of ES's
`icu_analyzer`. That removes any need for per-row config or up-front language
detection.

**Default: `pg_search` with the ICU tokenizer** (built into the ParadeDB dev
image — see `docs/postgres-extensions.md`). One BM25 index on `chunk.text`; ICU
does Unicode word segmentation across every script (spaces for Cyrillic/Latin,
dictionary for CJK); Tantivy gives real BM25 ranking. No `text_tsv`, no
`chunk.language` dependency.

`retrieval.text_ranker` picks the engine; a missing extension **downgrades
silently** (`GET /search/config` shows the effective one):

| `text_ranker` | Index on `chunk.text` | Script-agnostic? | Stemming | Needs |
|---|---|---|---|---|
| **`pg_search`** (default) | BM25 / Tantivy, ICU tokenizer | yes | optional per-analyzer | ParadeDB image (have it) |
| `pgroonga` | pgroonga, bigram/MeCab tokenizers | yes | no | `pgroonga` RPM |
| `bigm` | `pg_bigm` GIN | yes (bigrams; weak ranking) | no | `pg_bigm` RPM |
| `core` | `tsvector` GIN on the `text_tsv` column | **no** (per-language snowball; CJK falls back to `simple`) | yes, ~20 langs | nothing |

**Stemming vs. ICU:** plain ICU tokenization doesn't stem (`meeting` ≠
`meetings`). Acceptable for triage retrieval. If an English-dominant dataset
later wants stemming, `pg_search` supports named analyzers and the writer can
pick one from `chunk.language` — optional polish, not required.

**`chunk.language`** is filled when a detector runs. `lingua` (statistical
n-gram, no model, thousands/sec) as an extract-time step or enrichment is cheap;
use a confidence cutoff → `null`. It feeds result filtering ("Russian only"), the
optional stemmer choice, and display — not the search path.

**`text_tsv`** (only for `core`) is writer-populated with the config for
`chunk.language` (`simple` fallback), because `to_tsvector(<column>, unaccent(text))`
can't be an expression/generated index (not `IMMUTABLE`).

### Indexes

- `chunk`: **keyword index on `text`** per the ranker (BM25 for `pg_search`);
  `text_tsv` GIN only under `core`. HNSW(`embedding` `vector_cosine_ops`),
  btree(`dataset_id`,`filetype_group`), btree(`file_id`),
  GIN(`duplicate_file_ids` `jsonb_path_ops`).
- `mention`: btree(`chunk_id`), btree(`chunk_id`,`entity_id`),
  btree(`chunk_id`,`selector_type`) — all partial `WHERE chunk_id IS NOT NULL`
  (landed P0).

### `hybrid` fusion

RRF (reciprocal rank fusion) of the keyword ordering and the semantic ordering —
rank-only, so the two score scales don't need calibrating. Two ordered CTEs +
a join on `chunk.id`, `score = Σ 1/(k + rank_i)`.

## 6. Elasticsearch adapter — built, first-class

`ElasticsearchChunkRetrievalRepository` (`elasticsearch/repositories/chunk_retrieval.py`)
wraps the existing `text_chunks` index (BM25, kNN, RRF hybrid, the multilingual
analyzers in `mappings/analyzers.py` — unchanged) and satisfies the same ABC as
the Postgres adapter, including the same `search_text`/`search_semantic`/
`search_hybrid` shims, so `/search` and the chat agent don't know or care which
backend answers them.

**Entity / selector / `graph_expand` filtering is resolved live, never
denormalized onto the chunk doc.** This retires the old `sync-chunk-entities`
design (an O(files) batch job that didn't scale) without reintroducing it under
a new name:

1. `graph_expand`, if set, resolves via the injected `GraphRepository.traverse()`
   → a seed-entity-plus-neighbourhood id set (as the Postgres adapter already
   does for its own `graph_expand`).
2. Any of `entity_ids` / `entity_types` / `selector_types` / `selector_subtypes` /
   that graph set gets resolved by `PostgresMentionRepository.chunk_ids_for_filter`
   — one query against `mention`, driven by an index on `entity_id` /
   `selector_type` / `chunk_id`, bounded by *how many chunks mention the filter*,
   not by corpus size — into a concrete chunk-id list.
3. That list becomes one `{"terms": {"_id": [...]}}` clause, ANDed into the
   *same* ES query alongside the BM25/kNN/filter clauses (`extra_filter` param
   added to `search_text`/`search_semantic`/`search_hybrid`) — still one round
   trip to ES, no second query to merge client-side.

No ES mapping changes were needed; the old denormalized `entity_ids`/`entity_types`/
`selector_types`/`selector_subtypes` fields in the mapping are vestigial (a stale
per-doc filter on them is explicitly stripped before building the ES query, so
they can't silently reintroduce the staleness bug).

**Shared `chunk` substrate, regardless of backend.** `mention.chunk_id` needs
`chunk` rows to bisect against no matter which store answers search, so this
adapter also mirrors chunk **identity + spans + text** (never `embedding`) into
Postgres on every write — `upsert_chunk_spans` (`PostgresChunkRetrievalRepository`,
`include_embedding=False`). This is the one deliberate write that touches both
stores, and it's cheap: an id/offsets/text row, not a second copy of the vector
(the expensive part). `embed_text.py`'s `_chunk_store()` builds this wrapped
adapter automatically for `backend=elasticsearch`; `upsert_chunks` on either
adapter always keeps the `chunk` mirror current.

**Bounded filter size.** `chunk_ids_for_filter` caps at `graph_expand_entity_cap`
(default 10,000). Fine for a specific entity or a graph expansion; a very broad
category filter (e.g. every `selector_type=email` chunk in a huge dataset) can
hit the cap and under-filter. The documented upgrade path, if that proves to
matter at real scale, is denormalizing *only* the broad categorical fields
(`entity_types`/`selector_types`/`selector_subtypes` — small, bounded value
spaces) back onto the ES doc via an incremental dirty-chunk-set writer — never
`entity_ids` (unbounded cardinality, which is exactly what made the old design
not scale). Not built; no evidence yet that it's needed.

## 7. Configuration — and staying transparent

`Settings.retrieval` (`RETRIEVAL__*` env vars), **landed**:

```python
class RetrievalConfig(BaseModel):
    backend: RetrievalBackend = "postgres"          # postgres | elasticsearch
    text_ranker: TextRanker = "pg_search"           # pg_search | pgroonga | bigm | core
    graph_expand_entity_cap: int = 10_000
```

Default `pg_search` because the dev/compose image is ParadeDB (ships it). On a
plain PGDG image with nothing added, set `bigm` (one RPM) or `core` (nothing).

Two ways to see what's actually running — the backend should never be a guess:

- **Startup log:** `retrieval backend: postgres (text_ranker=pg_search)`.
- **`GET /api/search/config`** → `RetrievalConfigInfo`: `backend`, configured
  `textRanker`, `textRankerEffective` (downgraded if the extension is absent),
  `installedExtensions`, `graphExpandEntityCap`.

`TextChunkDatastoreDep` (`deps/elasticsearch.py::get_text_chunk_repository`) is a
factory reading `retrieval.backend`; it opens a Postgres session either way
(both adapters need one -- entity/graph data always lives there) and yields
`PostgresChunkRetrievalRepository` or `ElasticsearchChunkRetrievalRepository`,
both typed as `ChunkRetrievalRepository`. Routes and agent deps depend on the ABC
— no other route changes. `embed_text.py::_chunk_store()` mirrors the same
selection for the write path. `reset-text` and the app-startup `ensure_schema()`
call are backend-aware the same way.

## 8. FTS extensions

Full list, what each is for, and offline install: **`docs/postgres-extensions.md`**.
In short — the ParadeDB dev image already carries `pg_search` (+ `vector`,
`pg_trgm`, `postgis`, `unaccent`), so the default `pg_search` ranker needs
nothing added. A plain PGDG image adds one RPM (`pg_bigm`) or runs `core`. A
configured ranker whose extension is missing downgrades silently, visible at
`GET /search/config`.

## 9. Rollout — done

| Phase | Work |
|---|---|
| **P0** | `chunk` table, `mention.chunk_id`, `chunk_id_for` wired into `TextChunk.id`, migration `0019`. |
| **P1a** | `RetrievalConfig` (`RETRIEVAL__*`), startup log, `GET /search/config`, extension bootstrap. |
| **P1b** | `chunk.embedding`/`text_tsv` + HNSW/GIN/BM25 indexes (migration `0023`); `RetrievalQuery`/`GraphExpand` schema; `ChunkRetrievalRepository` ABC; `PostgresChunkRetrievalRepository`; embed pipeline writes `chunk` rows; `TextChunkDatastoreDep` factory. |
| **P2** | `mention.chunk_id` set inline at extraction time (`_assign_chunk_ids`, works for either backend); `backfill-mention-chunks` for pre-existing data; `graph_expand` agent tool (now `search_passages(entity_id, connected_hops)`; correspondence filters + `count_emails` added 2026-09-29). |
| **P3** | Re-embedded `rag` into Postgres end-to-end; found and fixed real bugs under real load (§10); `ElasticsearchChunkRetrievalRepository` built to the same ABC, live-resolved entity/graph filtering (§6), validated against a live ES cluster; both backends now switch with one setting. |

Switching backends is a **re-embed**, not a migration: reset the `TEXT_EMBEDDING`
enrichment for the dataset (clears its old chunks / the enrichment record, not
`extracted_text`), flip `RETRIEVAL__BACKEND`, re-run `embed-text`. Both backends'
`chunk`-table span mirror means `mention.chunk_id` doesn't need re-extraction —
`backfill-mention-chunks` (set-based) catches anything the inline assignment
missed.

### DB migrations (Alembic + raw SQL for the unstamped dev DB — [[dev-db-unstamped]])

- P0 (done): `chunk` table; `mention.chunk_id` + FK + partial indexes.
- P1: `CREATE EXTENSION pg_bigm` (`unaccent`, `vector` already present);
  `chunk.embedding` `vector(N)` + HNSW; `chunk.text_tsv` `tsvector` + GIN;
  `pg_bigm` GIN on `chunk.text`.

## 10. Performance

**Target: sub-second search at ~1M files (≈3–5M chunks).** What's below is
measured against the real `rag` corpus after the full re-embed (136,668 chunks,
31,052 files, one dataset) — real data, but ~4–7% of the file-count target, and
single-dataset, so multi-dataset selectivity (§10.3) is reasoned about, not yet
measured at scale. Re-benchmark against a corpus that's actually ~1M files before
calling the target met in production.

### 10.1 What's measured (Postgres adapter, `rag`, warm cache)

| Query | Plan | Time |
|---|---|---|
| BM25 keyword, Stage A (`pg_search`, `LIMIT 500`) | ParadeDB custom scan on `ix_chunk_text_bm25`, parallel, TopN-by-score — **not** a scan proportional to corpus size | ~17 ms |
| kNN semantic, Stage A (`LIMIT 500`) | Index scan on `ix_chunk_embedding_hnsw` | ~17 ms |
| Full `search()`, keyword, single dataset | Stage A + Stage B mention join (both index-driven) + hydrate + group | 80–140 ms |
| Full `search()`, keyword + `entity_ids` filter | Same, mention join narrows Stage B's ≤500-row candidate set | 55–75 ms |
| Full `search()`, **browse** (`text=""`) + `entity_ids` filter | see 10.2 | 80–110 ms (was 770–886 ms) |

All comfortably inside the 1-second budget at this scale, with headroom for
`pg_search`/HNSW to be genuinely sub-linear in corpus size (§10.1's Stage A rows
don't grow with total chunk count, only with `pool`).

### 10.2 A real bug the sub-second target caught

Initial `browse` mode (empty query + entity filter — no `@@@`/kNN predicate to
protect from a correlated clause, see §5) applied the `entity_ids` **AND-all**
filter as `NOT EXISTS (... EXCEPT ...)` directly against the full
`dataset_id`-scoped `chunk` table before any pool limit — correct, but a
per-candidate-row correlated subquery evaluated across the *whole scope*, not a
pre-narrowed set. Fine at the row counts where Stage A already narrows to 500
first (keyword/semantic/hybrid); **not** fine for browse, where nothing narrows
first — measured 770–886 ms at 136k chunks, an approach that gets *linearly
worse* as the dataset grows, the wrong shape for a 1M-file target.

Fix: browse now resolves `entity_ids`/`entity_types`/`selector_types`/
`selector_subtypes`/`graph_expand` via the **same** `PostgresMentionRepository
.chunk_ids_for_filter` the Elasticsearch adapter uses (§6) — one index-driven
scan of `mention` bounded by *how many chunks match the filter*, not by corpus
size — into a concrete id list, then `c.id = ANY(...)` (PK-indexed) before the
date-sort + limit. Result: 80–110 ms, same correctness (verified: identical
255-file result set before and after). This is also why the id-list resolve
uses `graph_expand_entity_cap` (10,000), not the small `pool` size, as its
cap — capping at `pool` first would silently return an arbitrary, not
most-recent, slice once an entity's mention count exceeds the pool.

**Takeaway for future query paths:** a correlated per-row subquery against
`mention` is only cheap once something upstream has already narrowed the
candidate set to hundreds of rows. Applied against a whole dataset-scoped (or
larger) scan, it degrades with corpus size — resolve to an id list via an
index-driven `mention` scan first instead, the same move both adapters now make.

### 10.3 Known unknowns at real 1M-file / multi-dataset scale

- **pgvector HNSW + `dataset_id` pre-filter.** `rag` is effectively the only
  populated dataset here, so the `WHERE dataset_id = ...` clause on the kNN
  query is a post-filter over the full HNSW walk, not a pre-filter — untested
  whether that stays fast when `dataset_id` is *highly* selective (many
  datasets, 1M files total). If it isn't, the fix is `hnsw.ef_search` tuning or
  pgvector's iterative index scan (`hnsw.iterative_scan`, 0.8+) so the graph
  walk resumes instead of exhausting its candidate budget on filtered-out rows.
- **HNSW build time / `maintenance_work_mem`** at 3–5M rows — a one-time cost
  (minutes to low hours depending on memory), not yet measured end-to-end at
  that row count; `rag`'s ~137k-row build was well under a minute.
- **`chunk_ids_for_filter`'s cap** (10,000, §6) — fine for a specific entity or
  a bounded graph expansion; a very broad category filter (every chunk of a
  common `selector_type` in a 1M-file corpus) can exceed it and under-filter.
  Denormalizing just the broad categorical fields is the documented, not-yet-built
  upgrade path if that turns out to matter (§6).
- **Postgres write throughput at 1M-file embed scale** — `rag`'s ~146k-chunk
  document half took ~4.5 min wall time (dominated by GPU inference, not the DB
  writes); the email half (~128k chunks) similarly GPU-bound. Not yet measured
  at 1M-file volume, but nothing in the write path (`upsert_chunks`'s
  batched `executemany`) is architecturally worse than what already ran here.

### 10.4 Storage

One copy of chunk text + one embedding, on whichever backend is active (`chunk`
for Postgres, the ES doc for Elasticsearch). The Elasticsearch adapter's
Postgres mirror (§6) is identity + spans + text, never `embedding` — the
expensive part is never duplicated.
