# Global search

**Status (2026-10-03):** built end to end on the `global-search` branch (§12): foundations, search
backend, search page, AI layer, scroll memory, Ctrl/⌘+K, breadcrumb trail.

**Decision.** `/search` becomes the single entry point for a corpus nobody
understands yet. It has two modes on one page:

- **No query: briefing.** What the selected datasets contain: composition, key
  players, time range, places, a sample of images, an LLM summary, and suggested
  starting searches. Clicking any item adds it as a filter.
- **Query: results.** One `GET /search/overview` call runs every lane (text,
  entities, images, faces, events, places, files) in parallel. Each lane has its
  own budget, and the response carries a layout from a rules router, so the page
  differs by query type without an LLM in the critical path.

The type-specific pages (`/images`, `/faces`, `/entities`, …) stay as they are.
The overview links into them ("See all →" and the lane chips) instead of
replacing them. Every query, and every filter added from the page, is stored as a **search** record with an
opaque id (`/search/[searchId]`). That record gives back/forward navigation
without putting query text in the URL. It is also the start of saved searches
and alerts (§7.4).

Terminology follows `docs/glossary.md`. New terms (**search**, **dataset
profile**) are added there too.

---

## 1. Why

- **Triage starts before anyone knows what to type.** A Google-style results
  page assumes a known item. Analysts first need the *shape* of a corpus (who,
  when, what kind of files) and only then go looking. The current `/search`
  page has nothing to show for an empty query.
- **The sidebar is a pile of viewers.** "Media" (Images, Faces) and "Explore"
  are split by file type, not by what you do there. Faces is really a review
  queue that feeds Persons. Images is really a search over one kind of content.
  One search entry point that fans out to every type removes the need for a
  Media group.
- **Each type already has a fast index.** Chunk BM25/HNSW, entity-name trigram,
  CLIP HNSW and face HNSW all exist. What's missing is one call that runs them
  together under a shared latency budget.

## 2. Non-goals

- Replacing the per-type pages or their filters. The overview previews them,
  and "See all →" hands off to them.
- A new retrieval store. Every lane uses the existing repository; chunk search
  stays behind `ChunkRetrievalRepository` (`docs/retrieval-architecture.md`).
- Cross-lane score fusion. Lanes are ranked against each other by a rule (§5),
  not by calibrating BM25 against CLIP against trigram scores.
- Storing result sets. A search record stores the *question*, never the answer
  (§7).
- Alerts and saved-search UI. The schema leaves room for them (§7.4); they are
  the next design.

## 3. The page

### 3.1 Briefing (no query)

Built entirely from the precomputed **dataset profile** (§6), so it loads in
milliseconds at any corpus size.

| Section | Contents | Click to filter |
|---|---|---|
| Composition | `filetype_group` mix, languages, total files and chunks | add a `filetype_group` / language filter chip |
| Timeline | monthly histogram of **content date** (email `date_sent`, else document `date_content_created`; never ingest time) | add a date-range filter chip (click or drag over bars) |
| Key players | top people and orgs by salience (§6.2) | entity chip (same as `?entityId=` today) |
| Correspondents | top `emailed` edges by volume | entity-pair chip |
| Places | top place entities, plus a mini map | place chip |
| Images | a sample of images, spread across CLIP clusters | opens `/images` similarity search for that image |
| Brief (AI) | LLM summary of the profile, plus 3–5 suggested starting searches | runs the suggested search |

### 3.2 Results (query)

The layout comes from the router (§5). Default lane order, with the strongest
lane promoted and empty lanes hidden:

| Lane | Preview | Source | "See all →" |
|---|---|---|---|
| Entity panel | best entity card plus related names | `EntityRepository.search_by_name` (trigram) | `/entities/{id}` |
| Text | top 5 files, highlighted snippets | `ChunkRetrievalRepository` hybrid | current `/search` text view |
| Images | strip of ~8 | CLIP text→image HNSW | `/images` |
| Faces | faces of name-matched persons | person name → face | `/faces` / `/persons/{id}` |
| Events | 3 rows | `event.title` trigram (new index) | `/events` |
| Places | 3 rows | `location.name` trigram (new index) | `/locations` |
| Files | filename matches | `file.filename` trigram (new index) | `/files/{id}` |

Each lane also reports **shape**: a content-date histogram and a `filetype_group` mix
over its candidate pool (≤500 hits, labelled "in top 500"). In triage, "how
much and where" matters as much as the top 10. Totals are capped ("500+");
there is never an exact `count(*)`.

Lane chips across the top (All · Text · Entities · Images · Faces · Events ·
Places) carry the active `searchId` to the type page.

### 3.3 Filtering from the page

Clicking something on the page (an entity, a date bar, a `filetype_group`)
adds it as a filter chip instead of navigating away. Filter chips AND together,
and every lane respects them. Each added filter creates a new search record
and a new history entry, so Back removes the last filter. A breadcrumb row
shows the trail.

## 4. API

```
POST /search/overview                     body: { query, datasetIds, filters, parentId }  → records it; { searchId, layout, text, entities, images, files, events, places }
POST /search/history/{searchId}/overview  → re-run a stored search (Back, reload) without recording it again
GET  /search/history/{searchId}           → the stored request (owner or admin; anyone else 404)
GET  /search/history                      → your recent searches, paginated
GET  /datasets/profile?datasetIds=…       → merged dataset profile (briefing)
POST /search/brief                        body: { searchId } → streamed LLM brief / answer (§8, not built)
```

`/search/overview` is a POST because `filters` is structured. Calling it **creates
or touches** a search record (§7.2) and returns its id. The frontend then
`pushState`s to `/search/{searchId}`. Responses are camelCase like every other
endpoint.

Overview response, per lane:

```jsonc
{
  "lane": "images",
  "status": "ok" | "timeout" | "error" | "empty",
  "items": [ ... ],            // lane-native public schema (ImagePublic, Entity, ...)
  "total": 37, "totalCapped": false,
  "shape": { "dateHistogram": [...], "filetypeGroups": {...} },
  "tookMs": 41
}
```

### 4.1 Execution

- Lanes run under `asyncio.gather`, **one `AsyncSession` per lane**, each
  wrapped in `asyncio.wait_for(lane, budget)` (default 1000 ms, set via
  `SEARCH__LANE_BUDGET_MS`). A lane that misses the budget returns
  `status: "timeout"`, and the UI shows a "See all →" link for it. One slow lane
  never holds the page.
- Query embeddings are computed **once per model** and shared. Jina (text) and
  CLIP-text (images) run concurrently. An in-process LRU keyed on `(model,
  query)` skips re-embedding on Back, re-runs and added filters.
- Access: content lanes (text, images, faces, files) get
  `access.scope(dataset_ids)` exactly as the per-type endpoints do. The entity,
  event and place lanes follow the glossary rule (the entity graph is shared
  and not access-controlled).
- Connection pool: a page uses up to 7 connections at once. Size the pool for
  `concurrent_users × 7` or put a semaphore on lanes. Check `pool_size` in
  the foundations step.

## 5. Routing

Two speeds. **The LLM never gates results.**

### 5.1 Rules router (in-request, <5 ms)

Runs inside `/search/overview` on the query string plus the lanes' own results,
and returns `layout: { hero, laneOrder, isQuestion }`.

| Signal | Effect |
|---|---|
| Query parses as a selector (email, phone, URL, handle; reuse `pyselectors` normalizers) | exact selector-entity lookup; entity panel is the hero |
| Top entity trigram similarity ≥ 0.6 | entity panel is the hero |
| `photo(s)/picture(s)/image(s) of …` | images lane first; CLIP query is the remainder |
| Starts with who/what/when/where/why/how, or ends in `?` | `isQuestion` → reserve the AI answer slot |
| Lane returned nothing | hidden |
| Otherwise | lanes ordered by best normalized in-lane rank (top hit's score relative to the lane's own score distribution), ties broken by default order |

Most of the visible "the page changes per query" effect comes from the results
themselves, which is cheap and deterministic.

### 5.2 LLM layer (async, after paint)

One call to the **backend's default LLM** (`LLM__*`, the same as chat) per new
search. It is cached on the search record, so it is never re-run on Back. It
returns:

- **intents** (confirming or overriding `isQuestion`)
- **extracted filters**: dates, entities, `filetype_group`. Shown as a
  suggestion chip ("Emails · 'contract' · March 2026 · Apply"), **never
  auto-applied**, so the page never reshuffles while someone is reading it.
- **answer**: only when it's a question, grounded in the overview's own hits.
  See §8.

Measured 2026-10-03 on local Qwen3.8-27B (thinking off, idle GPU): ~0.4 s for
a routing classification, with sensible output on 4 probe queries. Fine after
paint. In front of results it would double page time and make search depend on
GPU contention from chat and extraction.

AI surfaces use the annotation colour (amber), per `feedback_annotation_color`.

## 6. Dataset profile

The briefing's data source, and the reason the empty-query mode is fast.

### 6.1 Storage

`dataset_profile` (one row per dataset, `dataset_id` PK). It is dataset
content, so it is access-gated like chunks:

```
dataset_id, date_computed, profile_version,
file_count, chunk_count,
filetype_group_counts   jsonb   {group: n}
language_counts         jsonb
date_histogram          jsonb   [{month, n}]        -- content date (glossary), not ingest time
top_people_orgs         jsonb   [{entity_id, display_name, entity_type, files}] (top 200, non-bulk files)
top_selectors           jsonb   same shape
top_places              jsonb   same shape
top_correspondents      jsonb   [{from_id, to_id, n}] (top 100)
image_sample_ids        jsonb   [image_id]            -- spread over CLIP space
brief                   jsonb   {text, model, date_generated}  -- cached LLM summary
```

It is computed by `cipher profile-dataset --dataset …`, wrapped in
`run_recorder.record_run` like other enrichment steps, and run automatically at
the end of an enrichment pipeline run. It is a full recompute, not incremental.
It reads each table once with `GROUP BY`, so its cost is batch-time, not
query-time.

**Multi-dataset briefing** merges profiles in the API: counts sum, histograms
add, and top-entity lists merge over the union of each profile's top 200. The
union is approximate for the long tail and exact for anything that is
top-200 in at least one dataset. That is the documented tradeoff.

### 6.2 Salience, not frequency

Measured on `rag` (2026-10-03), ranking by raw distinct-file count:

- **Selectors dominate.** The mailbox owner's two addresses are in 15,050 and
  13,280 of 30,515 files. Fix: selectors, places, and people/orgs are
  **separate lists**, so identifiers never crowd out people.
- **Among people/orgs, bulk mail dominates**: Medium, Towards Data Science,
  Quora, Google. df·idf variants (`f·ln(N/f)`, `f·ln(N/f)²`) don't reorder
  them, because everything is far below the idf peak. Fix: count **non-bulk
  files only**, using the data's own categories: drop files whose
  `source_tags` include `promotions`/`updates`/`social`/`forums`, or whose
  `message_states` include `spam`. The result is Nick, Nick B, Megan Flick,
  Bolton, Liz, Dolce, Verizon, cathi bolton. These are the people in the
  mailbox. The query took 382 ms; it is batch-time only.
- A dataset with no source categories falls back to all files. The bulk
  category list is a setting, not hard-coded.
- Unresolved name variants ("Nick", "Nick B", "Nicholas") show up as separate
  rows. That is a resolution backlog, not a ranking bug. The briefing links
  them to the Resolve tab and does not merge them itself.

There is no special "account owner" concept. They rank high because they
genuinely are central.

## 7. Search records

### 7.1 Table

`search`:

```
id                 str (opaque, e.g. "s_" + 12 base32 chars)
user_id            from CurrentUserDep, never the body
query              text
dataset_ids        jsonb   -- as requested; re-intersected with access on every load
filters            jsonb   -- filter chips: entity ids, date range, filetype_groups, ...
parent_id          str | None   -- the search this one was narrowed from (breadcrumbs)
fingerprint        str     -- hash(user_id, normalized query, sorted datasets, filters)
llm_plan           jsonb | None -- cached §5.2 output
run_count          int
date_created, date_last_run
date_saved         timestamp | None   -- saved search (later)
name               str | None         -- saved search label (later)
```

Results are **never** stored. Opening a search id re-runs it. That is cheap
(§10) and keeps the table small. It also avoids a second, unprotected copy of
dataset content.

### 7.2 Write path

`/search/overview` upserts on `fingerprint`: re-running the same question
bumps `run_count` and `date_last_run` instead of inserting. The table grows
with **distinct** questions, not page loads. Back/forward re-reads an existing
id and does not write.

### 7.3 Size and retention

- A row is roughly 0.5–1 KB.
- A heavy estimate is 50 analysts × 200 distinct searches/day × 250 days ≈
  2.5 M rows/year ≈ 1–2.5 GB. That is small next to `chunk` (an embedding per
  row).
- Unsaved history is short-lived: it is pruned after
  `SEARCH__HISTORY_RETENTION_DAYS` (default **14**) by
  `cipher prune-search-history`. Its job is Back/forward, breadcrumbs and
  "recent searches", not an archive. Saved searches (`date_saved` set) are
  never pruned. At 14 days the table stays at a few hundred thousand rows.
- An index on `(user_id, date_last_run desc)` serves history, and a unique
  index on `fingerprint` serves the upsert. If the table ever gets large enough
  to matter, partition by month on `date_created`. That is not needed at the
  estimate above.
- **Privacy:** a search record is readable only by its owner and by admins
  (`user.is_admin`). `GET /search/{id}` returns 404 to anyone else, so an id is
  not a sharing mechanism. `/search/history` lists only your own records. An
  admin view of any user's history is a separate admin-only endpoint
  (`AdminOnly`), added with the user page.
- A deleted dataset leaves stale ids in `dataset_ids`. They drop out at load,
  when datasets are re-intersected with access, so no cascade is needed.

### 7.4 Path to knowledge management (next design)

The record is designed so the following are additive columns or tables, with
no migration of meaning:

- **Saved searches**: set `date_saved` and `name`; a "Saved" list in the
  sidebar under Search.
- **Alerts**: a separate `search_alert` table (`search_id`, schedule,
  `watermark`). Re-run on a schedule, restricted to content newer than the
  watermark (`chunk`/`file` `date_loaded`), and notify on new hits. It stores
  only the watermark, consistent with "never store results".
- **User page**: your own tags, recent searches, saved searches and alerts in
  one place. It reads `/search/history`; nothing new is needed in the search
  record.
- **Sharing**, if it is ever wanted, would be an explicit grant, never an
  open id. A grantee would re-run the search with *their* access (§4.1).

## 8. Chat hand-off

- The question answer (§5.2) is generated through the existing `/chat`
  endpoint in a **no-tools mode**. The overview's top hits are passed as
  context, so it is grounded in the hits on screen and runs no second search.
  Citations use chat's footer citation pills.
- **Continue in chat** opens `/chat` with that conversation already started:
  the user's query, the answer, and the cited record ids. It is handed over
  through `useChatStore` (zustand, not the URL), with `datasetIds` copied from
  the search. The agent continues with tools on.
- The briefing's LLM summary uses the same path with the profile as context,
  and is cached on `dataset_profile.brief` per `profile_version`.

## 9. Navigation and Back

Requirement: Back works through queries and added filters, and returning from a
result restores the page, without query text or data in the URL.

1. **`/search/[searchId]`** gives every query and added filter its own history entry.
   The URL is an opaque id (the "ID-specific page" exception in CLAUDE.md).
   A new search uses `window.history.pushState`, which Next 16 integrates with
   `usePathname`.
2. **Cache Components + `<Activity>`** (Next 16.3.1 / React 19.2.5 are
   installed). With `cacheComponents: true`, a route you navigate away from is
   hidden, not unmounted. Coming back from `/files/{id}` restores results and
   scroll without refetching (up to 3 routes are kept). This is an **app-wide**
   config change, so it is its own step with a regression pass. Transient
   UI (popovers, dialogs) must reset via `useLayoutEffect` cleanup per
   `node_modules/next/dist/docs/01-app/02-guides/preserving-ui-state.md`.

Rejected: `?q=` in the URL (exposes the query, against preference); a
`history.state` payload alone (not restorable after reload, and Next's router
owns `history.state`).

## 10. Performance

**Target:** briefing < 200 ms; overview p95 < 1 s (hard ceiling is the lane
budget); LLM content streams after paint and is not counted.

### 10.1 Measured (2026-10-03, warm, `rag` + 3 small datasets: 76k chunks, 38k entities, 31k files, 473k mentions)

| Query | Time | Scales with |
|---|---|---|
| Chunk BM25 top 50 (`pg_search`) | 41 ms | pool, not corpus |
| Chunk BM25 `count(*)` | 35 ms | matches → **cap it** |
| Chunk HNSW top 50, unfiltered | 12 ms | pool |
| Chunk HNSW, filtered to a 356-chunk dataset, `iterative_scan` on | **162 ms** | **the size of the rest of the index** |
| Same, `iterative_scan` off | 5 ms, **0 rows** | (wrong answer) |
| Entity name trigram top 10 | 2 ms | matches |
| Image CLIP HNSW top 24 | 5 ms | pool |
| `file.filename ILIKE` (no index, seq scan) | 15–40 ms | **corpus, linear** |
| `event.title` / `location.name` ILIKE (no index) | 2 ms | **corpus, linear** |
| Top entities by distinct file count (`mention` GROUP BY) | **902 ms** | **mentions, linear** → precompute (§6) |
| `filetype_group` breakdown / monthly histogram (measured on `file.date_created`; content date needs the email/document join, so slower) | 12–19 ms | files → precompute anyway |
| LLM routing call (Qwen3.8-27B local, idle) | ~400 ms | GPU load → keep async |

### 10.2 Fixes found by the benchmark (landed 2026-10-03)

- **Trigram indexes** on `file.filename`, `event.title`, `location.name`,
  `person.name` (migration `0042`, built `CONCURRENTLY` so a live `file` table
  keeps taking ingest writes). Filename search: 15–40 ms full scan → <0.1 ms.
- **Image similarity search** sets `hnsw.iterative_scan = strict_order` (strict,
  because it paginates by offset). This is defensive: at 11k images the planner
  still chooses a full scan for a dataset-filtered query, so an under-return
  couldn't be reproduced either way. It matches chunk and face search.
- **Generic-plan bug in chunk search (affects the existing search page).**
  asyncpg reuses prepared statements. After 5 runs on a pooled connection,
  Postgres switches to a generic plan, and pg_search can then no longer use the
  dataset filter well: **37 ms → 293 ms** for the same query.
  `search()` now sets `plan_cache_mode = force_custom_plan`.
- **Keyword `total`** no longer runs an uncapped exact count. It is skipped
  when the 500-candidate pool wasn't full (the count is then already exact).
  Otherwise it counts files over the first 5,000 matching chunks and reports
  `totalIsExact = false` above that (the UI already shows "N+").
  Visible change: "bolton" on `rag` shows 3,715+ instead of 4,070.

### 10.3 Scale benchmark (measured 2026-10-03)

`scripts/make_scale_bench.py` builds `scale-bench-10x (synthetic)` (10 copies of
`rag`) plus 50 × `scale-bench-small-NN (synthetic)` (300 random `rag` files
each). The corpus is then **875k chunks, 351k files, 6.5M mentions, 11k images,
55 datasets, 13 GB**. Bulk mode drops the chunk search indexes and rebuilds them
once at the end (7.4 min, single-threaded at 6 GB working memory). Live index
upkeep made one copy take more than 12 minutes.

`scripts/bench_global_search.py`: each lane through the real repositories,
alone and all in parallel, 6 queries × 5 repeats, warm. It uses stored
embeddings, so it measures database time only. §10.4 adds the end-to-end API numbers.

| Scope | Page p50 / p95 (all lanes parallel) | Slowest lane p95 |
|---|---|---|
| `rag` (30k files) | 258 / 444 ms | keyword 408 ms (common terms still count) |
| one small dataset (300 files) | 130 / 200 ms | hybrid 177 ms |
| `10x` (305k files) | 189 / 248 ms (**was 847 / 1,137 ms** before the fixes above) | keyword 220 ms |
| all datasets | 137 / 202 ms | entities 151 ms |

Semantic search filtered to a small dataset is 44–55 ms p50, so iterative
scan holds up and partitioning isn't needed at this scale. Images run ~55 ms
filtered and ~9 ms unfiltered. Entities are a flat ~110 ms (shared graph, not
dataset-scoped). Files, events and places are under 5 ms.

**What still scales with corpus size:** keyword ranking cost follows how
common a term is *across all datasets*. "bolton" or "machine learning" take
~100–125 ms even inside a 300-file dataset, because the BM25 index walks every
corpus-wide match before applying the dataset filter. The next lever, if 1M+
files needs it: index `dataset_id` in the BM25 index as an untokenized keyword
field, and express the scope as a term query, so the filter is intersected
inside the index. The current index tokenizes the UUID, so a term query on it
matches nothing. That is an index rebuild, deferred until a benchmark needs
it.

**Environment caveat:** the dev container runs stock Postgres memory settings
(`shared_buffers` 128 MB, `maintenance_work_mem` 64 MB, `/dev/shm` 1 GB).
Production tuning would only improve these numbers.

### 10.4 End-to-end through the API (2026-10-03)

`POST /search/overview` on the 875k-chunk corpus, 8 different queries per scope, a cold
embedding cache (API restarted), every lane included:

| Scope | Page p50 / p95 | Text lane p50 (incl. query embedding) |
|---|---|---|
| `rag` | 408 / 670 ms | 379 ms |
| one small dataset | 356 / 675 ms | 298 ms |
| `10x` | 371 / 537 ms | 316 ms |
| all datasets | 348 / 397 ms | 283 ms |

No lane timed out. Each lane embeds its own query, so name lookups never wait on
inference. Re-running a search (Back, reload) hits the embedding cache: ~150 ms.

- **The biggest remaining cost is query embedding on CPU.** `.env` sets
  `TEXT_EMBEDDING_MODEL_DEVICE=cpu`, which is roughly 150–200 ms of the text lane.
  On the GPU it should be tens of ms. That's a deployment choice, not a code change.
- **CLIP scores aren't relevance.** Absolute text→image similarity doesn't track
  relevance: "invoice" scored 0.29 and "photos of the beach" 0.277 on `rag`. So
  there's no threshold. Images lead only for an image query ("photos of …") and
  otherwise sit last as a "visually related" strip. A per-dataset calibration
  (score relative to the query's own score distribution) is the upgrade if needed.
- **Dataset profile:** `cipher profile-dataset` takes 5 s on `rag` and 19 s on the
  305k-file dataset. `GET /datasets/profile` takes 36 ms for one dataset and 86 ms
  merged over all 55.

## 11. Information architecture

```
Home
Workspace:  Datasets · Search ▸ (Images, Faces, Saved later) · Chat
Explore:    Entities · Graph · Persons · Locations · Events
Help
```

The Media group goes away. `NAV` in `frontend/lib/nav.ts` drives both the
sidebar and the Home launcher, so the change lands in one place. Search becomes
a collapsible item.

**⌘K quick search**: a header palette that runs only the cheap lanes
(entity names, filenames; < 50 ms) and ends with "Search everything for 'x'"
→ `/search`.

## 12. Rollout

| Step | Scope |
|---|---|
| **Foundations** ✅ | Migration `0042` (trigram indexes, `search`, `dataset_profile`); image `iterative_scan`; chunk-search generic-plan fix + bounded keyword count; scale-bench datasets and script (§10.2–10.3) |
| **Search backend** ✅ | `cipher profile-dataset` + `GET /datasets/profile`; `POST /search/overview`; `GET /search/history`, `GET /search/history/{id}`, `POST /search/history/{id}/overview` (re-run without recording); `cipher prune-search-history`; rules router; end-to-end numbers (§10.4) |
| **Search page** ✅ | `features/global-search/`: `/search` (briefing), `/search/[searchId]` (results; lanes in layout order, featured lane first, text-lane timeline, filter chips, Back = previous search), old text search moved to `/search/text`; "See all" hands the query to the type page through a short-lived in-memory handoff (no URL); sidebar: Search expands to Emails & documents / Images / Faces, Media group removed. Not yet: breadcrumbs of the narrowing trail, a files-lane "See all" |
| **AI layer** ✅ | `POST /search/history/{id}/assist` (answer for questions from the top 8 passages with `[n]` citations; suggested narrower search) + `GET /datasets/profile/brief` (summary + starting searches); backend default LLM, thinking off for local Qwen; cached on `search.llm_plan` / `dataset_profile.brief`. Dates, file types and the topic are read by rules (`read_query_filters`) -- the local model was unreliable at them; the model only supplies the answer and names, and a name must appear in the typed query. Continue in chat seeds the conversation with the question + answer + sources |
| **Scroll memory** ✅ | Not `cacheComponents`: the app scrolls inside the layout's `[data-page-scroll]` div, which Activity/browser restoration don't cover. `useRememberedScroll(searchId)` saves/restores per search |
| **Quick search** ✅ | Ctrl/⌘+K palette in the root layout: "Search everything for …" (Enter), recent searches, pages. Filters locally while typing -- no request per keystroke (project rule) |
| **Breadcrumb trail** ✅ | `trail` on the overview response (recursive walk of `parent_id`, owner only); each step labelled by what it added |

## 13. Open questions

- The bulk-category list (§6.2) is tuned on Gmail categories. Check it on the
  phone dataset and any non-Gmail mail.
- Is the faces lane worth having for text queries (it only works through person
  names), or should it appear only when the query is a photo upload (a future
  "search by image" input in the search bar)?
- Exact facet counts on text hits: ParadeDB aggregates over the BM25 index
  could replace the "in top 500" approximation if analysts need true totals.
