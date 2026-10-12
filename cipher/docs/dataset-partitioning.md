# Dataset partitioning

**Status:** design, 2026-10-03. Not built. To implement when the corpus heads to
several million files (§1). The probe results in §5 were measured on the dev DB
(pg_search 0.21.4, pgvector 0.8.1, Postgres with the ParadeDB image).

**Decision.** Partition the tables that belong to a dataset (`file`,
`extracted_text`, `chunk`, `mention`, `mention_relationship`) by
**`HASH (dataset_id)` into 32 buckets**. The entity graph (`entity`,
`entity_relationship`, `location`, `person`, …) is shared across datasets and
stays unpartitioned. A query scoped to some datasets reads only their buckets.
A query across all datasets fans out to at most 32 per-bucket index searches
and merges them. One dataset that outgrows its bucket gets that bucket
sub-partitioned by `hash(file_id)` (§3.3).

Terminology follows `docs/glossary.md`. Related: `docs/retrieval-architecture.md`
(chunk search), `docs/global-search.md` §10.3 (the benchmark this builds on).

---

## 1. Why, and when

Measured 2026-10-03 at 875k chunks / 351k files / 6.5M mentions / 55 datasets
(`docs/global-search.md` §10.3): every search lane is fine, with the page at
p95 ≤ 444 ms. Partitioning is **not needed at that size**. What grows:

- **`mention` is the big table.** About 18 rows per file (`rag`: 71% named-entity
  extraction from body text, 20% email headers, 9% regex selectors). Several
  million files means ~100M mentions and 10M+ chunks.
- **Keyword ranking cost follows corpus-wide term frequency**, not the size of
  the dataset being searched: ~100 ms for a common word inside a 300-file
  dataset at 875k chunks. One shared BM25 index sees every dataset's postings.
- **Deleting a dataset** is a cascading delete through millions of rows.
- **Index builds and vacuum** on single multi-hundred-GB tables become slow
  operations that block or degrade everything.

**Triggers to start** (any one): the global-search benchmark misses p95 1 s on
any scope; `mention` passes ~50M rows; a single HNSW rebuild passes ~1 hour;
dataset deletes start timing out.

**Try first, because they're cheaper** (each is independent of partitioning,
and still needed after it):

1. Index `dataset_id` in the BM25 index as an untokenized `keyword` field, and
   add `dataset_id @@@ paradedb.term('dataset_id', :id)` next to the existing
   `dataset_id = ANY(...)`. The probe (§5) showed the filter moving *inside*
   the index. Today it is applied after the index lookup. This is a BM25
   rebuild only.
2. Tune Postgres memory. The dev container runs stock settings
   (`shared_buffers` 128 MB, `maintenance_work_mem` 64 MB, `/dev/shm` 1 GB).

## 2. Scope

| Partitioned (dataset-owned, large) | Not partitioned |
|---|---|
| `file`, `extracted_text`, `chunk`, `mention`, `mention_relationship` | the entity graph: `entity`, `entity_relationship`, `entity_match`, `entity_relationship_candidate`, `organization`, `selector`, `person`, `location`, `event`, `face`, `image` (keyed by sha256, shared across datasets) |
| | small dataset-scoped tables: `dataset_profile`, `enrichment_run`, `user_dataset_access`, `search`, `tag`, `comment`, `message`, `contact` |

`message` and `contact` are dataset content but small. Revisit them if either
reaches millions of rows.

## 3. Scheme

### 3.1 Why hash buckets

| Option | Scoped query | All-datasets query | Dataset delete | Ops cost |
|---|---|---|---|---|
| **HASH(dataset_id), 32 buckets** ✅ | reads 1 bucket per dataset | ≤ 32 index searches, merged | delete within 1 bucket (batched) | none per dataset |
| LIST, one partition per dataset | reads exactly 1 partition | **one index search per dataset**: hundreds | `DROP` partition (instant) | DDL on every dataset create |
| No partitioning + BM25 keyword field | in-index filter | 1 search | cascading delete | none |
| Citus / sharding | same as hash, across nodes | parallel across nodes | per shard | a cluster to run |

Global search defaults to *all accessible datasets*, so the all-datasets column
decides it: per-dataset partitions make the default query cost grow with the
number of datasets. Hash buckets cap that fan-out at 32 no matter how many
datasets exist. 32 is a starting point: it can be changed later only by
re-partitioning, so pick it once from the benchmark (§8). 16 is cheaper for
all-datasets queries; 64 gives finer pruning.

### 3.2 Partition key

`dataset_id` is already a column on `file`, `chunk`, `mention` and
`mention_relationship`. **`extracted_text` has no `dataset_id`**, so it must
be added and backfilled from `file` first (§4). Rows never change dataset, so
the key is immutable and no row ever moves between partitions.

### 3.3 One dataset outgrowing its bucket

A hash partition can itself be partitioned. If one dataset dominates a bucket
(rule of thumb: > 25% of all rows), sub-partition *that bucket* by
`HASH (file_id)` into 8. Queries scoped to that dataset then fan out across 8
sub-partitions instead of scanning one huge one. Other datasets in the bucket
are unaffected. This is a per-bucket migration (detach, re-partition, copy,
attach), done only when needed.

## 4. Keys and foreign keys

Postgres requires the partition key in every primary key and unique
constraint, and a foreign key into a partitioned table must reference a unique
key, so **it must include `dataset_id`**.

| Table | Primary key now → after | Other unique constraints |
|---|---|---|
| `file` | `id` → `(id, dataset_id)` | `uq_dataset_uri (dataset_id, uri)` already contains it |
| `extracted_text` | add `dataset_id` (backfill from `file`), PK → `(…, dataset_id)` | |
| `chunk` | `id` → `(id, dataset_id)` | |
| `mention` | `id` → `(id, dataset_id)` | |
| `mention_relationship` | `id` → `(id, dataset_id)` | |

Every foreign key into those tables becomes composite. Current list, from
`pg_constraint`:

| From | Column → target | On delete | Change |
|---|---|---|---|
| `file.parent_id` | → `file` | cascade | `(parent_id, dataset_id)` (same dataset) |
| `extracted_text.file_id` | → `file` | cascade | `(file_id, dataset_id)` |
| `chunk.file_id` | → `file` | cascade | `(file_id, dataset_id)` |
| `mention.file_id` | → `file` | set null | `(file_id, dataset_id)` |
| `mention.chunk_id` | → `chunk` | set null | `(chunk_id, dataset_id)` |
| `mention_relationship.file_id` | → `file` | set null | `(file_id, dataset_id)` |
| `mention_relationship.src_mention_id` / `dst_mention_id` | → `mention` | cascade | `(…, dataset_id)` |
| `entity_match.mention_id` | → `mention` | cascade | `(mention_id, dataset_id)` (has `dataset_id`) |
| `entity_relationship_candidate.evidence_mention_id` | → `mention` | set null | `(…, dataset_id)` (has `dataset_id`) |
| `event.file_id` | → `file` | set null | `(file_id, dataset_id)`; `event.dataset_id` is nullable, so the FK isn't enforced on dataset-less events (MATCH SIMPLE) |
| `location.file_id`, `message.file_id`, `contact.file_id` | → `file` | set null | add `dataset_id` (backfill from `file`), then composite |

**`ON DELETE SET NULL` with a composite FK:** Postgres 15+ supports
`ON DELETE SET NULL (file_id)`, which nulls only the id column and keeps
`dataset_id`. Use that form. A plain `SET NULL` would also null `dataset_id`,
which is NOT NULL on most of these tables.

**Code impact:** `cipher-datastores` repositories that look a row up by `id`
alone still work, because Postgres scans every bucket's PK index. But they are
up to 32 index probes instead of 1. Hot paths (`/files/{id}`, chunk hydration
in `search()`, mention spans) should pass `dataset_id` too so the lookup is
pruned to one bucket. Grep for `.where(FileTable.id ==`, `ChunkTable.id`,
`MentionTable.id` and the raw SQL in `chunk_retrieval.py`, `mention.py`,
`entity_match.py`.

## 5. Indexes (probe results, 2026-10-03)

A throwaway schema with a 2-bucket hash-partitioned `chunk` (2,000 rows, then
dropped):

| Question | Result |
|---|---|
| BM25 (`pg_search`) index on a partitioned parent? | ✅ Created once on the parent, one index per partition. |
| Partition pruning with BM25? | ✅ `dataset_id = 'ds1'` scanned only that dataset's bucket. |
| Is the dataset filter applied inside the BM25 index? | ❌ Applied after the index lookup (`heap_filter`). Same as today on the unpartitioned table, which is why common words cost ~100 ms even in a small dataset. |
| With `dataset_id` as a `keyword`-tokenized field + `paradedb.term`? | ✅ Runs inside the index (correct hit count). ❌ But a `@@@` predicate alone doesn't prune partitions. **Write both predicates.** |
| Fast top-N ranking (`TopNScanExecState`)? | ❌ On the partitioned table the plan was `NormalScanExecState` + Append + Sort: every match in every scanned bucket is scored, then sorted. The unpartitioned table uses TopN. This is the main risk. Re-check on a large partitioned table and a newer pg_search before relying on it. |
| HNSW (pgvector) on a partitioned parent? | ✅ One index per partition, merged with **Merge Append**, in order, with a limit. |

**Mitigation for the TopN loss** if it holds at scale: rank per bucket in SQL,
then merge, so each bucket keeps its own top-N plan:

```sql
SELECT id, score FROM (
  SELECT id, score FROM chunk_p03 WHERE ... ORDER BY score DESC LIMIT :pool
  UNION ALL
  SELECT id, score FROM chunk_p17 WHERE ... ORDER BY score DESC LIMIT :pool
) per_bucket ORDER BY score DESC LIMIT :pool
```

The repository computes which buckets the requested datasets hash to (the same
hash Postgres uses: `satisfies_hash_partition`, or a lookup table maintained
when a dataset is created). `ChunkRetrievalRepository` is the only place that
writes this SQL, so the change stays local.

HNSW per partition needs nothing new: `iterative_scan` is already set, and
`plan_cache_mode = force_custom_plan` (already in `search()`) keeps pruning
working with prepared statements.

**Index builds** become per-partition: smaller and individually rebuildable.
`drop_search_indexes` / `ensure_schema` in `chunk_retrieval.py` must loop
over partitions, or operate on the parent (which cascades).

## 6. Query patterns after partitioning

| Pattern | Today | After |
|---|---|---|
| Search one dataset | one index, filter after lookup | one bucket's index (≈ 1/32 of the postings) |
| Search a few datasets | same | ≤ a few buckets |
| Search all datasets (global search default) | one index | ≤ 32 per-bucket searches, merged (§5 mitigation) |
| `/files/{id}` without `dataset_id` | 1 PK probe | ≤ 32 PK probes (pass `dataset_id` on hot paths) |
| Entity → its mentions (dossier, resolution) | `ix_mention_dataset_entity` etc. | same index per partition. A cross-dataset entity reads every bucket. These are index lookups, so cheap, but more of them. |
| Delete a dataset | cascade through all rows | cascade within one bucket, run in batches (e.g. 50k rows per transaction) by a CLI command, not in a request |
| Dataset profile computation | full-table `GROUP BY` | one bucket |

## 7. Migration

The dev DB can take downtime, so: build alongside, copy, swap.

1. **Prerequisites** (separate, small revisions): add `dataset_id` to
   `extracted_text`, `location`, `message`, `contact` with backfill from
   `file`; add the BM25 `dataset_id` keyword field (§1).
2. **Create** `file_p`, `extracted_text_p`, `chunk_p`, `mention_p`,
   `mention_relationship_p` as `PARTITION BY HASH (dataset_id)` with 32
   partitions each, composite PKs, no secondary indexes yet.
3. **Copy** in dependency order (`file` → `extracted_text` → `chunk` →
   `mention` → `mention_relationship`), with `INSERT … SELECT` per source
   dataset. Same bulk approach as `scripts/make_scale_bench.py`: no search
   indexes during the copy, temp tables with primary keys for any membership
   test (an `IN (subquery)` bigger than `work_mem` turns quadratic).
4. **Build indexes** on the parents, single-threaded with a large
   `maintenance_work_mem`, or parallel if `/dev/shm` is raised to match
   (see `project_postgres_shm`).
5. **Swap:** rename old tables to `*_old`, new to the real names; recreate the
   composite FKs from §4 (`NOT VALID`, then `VALIDATE CONSTRAINT`, so
   validation doesn't hold a long lock).
6. **Verify** row counts per dataset, run the benchmark (§8), then drop
   `*_old`.

**Alembic:** one revision per step, idempotent. Step 3 is a CLI command
(`cipher partition-migrate --dataset … | --all`), not inline migration SQL,
so it can be resumed per dataset. `schema.py` `EXTRAS` must create the
partitions for an empty DB (`create-tables --stamp-head`), because
SQLAlchemy's `create_all` won't create hash partitions on its own. Declare the
parents with `postgresql_partition_by='HASH (dataset_id)'` in `__table_args__`.

**Production / online:** if downtime isn't acceptable later, copy with
logical replication or a dual-write window. That's out of scope until a
deployment needs it.

## 8. Validation

Before *and* after, with `scripts/make_scale_bench.py --copies 100` (~3M files,
~7.6M chunks, ~56M mentions, ~100 GB; disk had 491 GB free on 2026-10-03) and
`scripts/bench_global_search.py`:

- Overview page p95 < 1 s for every scope (one small dataset, one huge
  dataset, all datasets).
- Common-word keyword search in a small dataset: should drop well below
  today's ~100 ms (≈ 1/32 of the postings).
- All-datasets keyword search must **not** regress past the budget. This is
  the TopN risk in §5, and the go/no-go for this design.
- `/files/{id}`, entity dossier, resolution queue: no visible regression.
- Dataset delete of a 300k-file dataset: completes in batches without blocking
  search.

If all-datasets keyword search regresses and the per-bucket `UNION ALL`
doesn't recover it, the fallback is the Elasticsearch adapter for chunk search
(`retrieval-architecture.md` §6, already built). ES shards by design, and the
Postgres tables could then stay unpartitioned longer.

## 9. Implementation checklist

- [ ] BM25 `dataset_id` keyword field + both predicates in `_index_scope` (useful now, independent of partitioning)
- [ ] `dataset_id` on `extracted_text`, `location`, `message`, `contact` (+ backfill)
- [ ] Benchmark at `--copies 100` on the unpartitioned schema (baseline)
- [ ] Partitioned parents + 32 partitions; `EXTRAS` in `schema.py` for empty DBs
- [ ] `cipher partition-migrate` (resumable per dataset)
- [ ] Composite FKs (`NOT VALID` → `VALIDATE`), `ON DELETE SET NULL (col)`
- [ ] `chunk_retrieval.py`: per-bucket ranking if TopN is lost; index helpers loop partitions
- [ ] Hot-path lookups pass `dataset_id`
- [ ] `cipher delete-dataset` batched
- [ ] Benchmark again; record results here, as `global-search.md` §10.3 does

## 10. Open questions

- Does pg_search keep TopN on a large partitioned table, or in a newer
  release? This decides whether §5's `UNION ALL` is needed.
- 16, 32 or 64 buckets: decide from the `--copies 100` benchmark.
- Should `face` (per-file detections) be partitioned too? It's keyed by
  content, not dataset, today. Leave it until it's large.
