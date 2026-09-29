# CIPHER glossary

The canonical vocabulary for CIPHER. One term, one meaning, everywhere: schemas,
tables, API, CLI, frontend, docs, chat agent, and these conversations. If a term
here and the code disagree, that's a bug in one of them — fix it, don't fork the
word.

**Audiences.** Developers reference it when naming things; the chat agent and
Claude Code use it to stay consistent with the data model; the in-app docs page
(`frontend/app/(app)/docs`) renders a Glossary section from it for analysts.

**Casing rule.** Backend / database / `cipher-schemas` use `snake_case`
(`filetype_group`, `selector_type`). The frontend uses the same words in
`camelCase` (`filetypeGroup`, `selectorType`). Only the casing changes across the
boundary — never the word. Enum *values* are lowercase strings
(`"document"`, `"communicates_with"`); the Postgres enum columns store the member
*name* (uppercase) because they use `Enum(native_enum=False)`.

This file is living. Add a term the first time it needs defending in review.

---

## Corpus & ingestion

| Term | Meaning |
|---|---|
| **dataset** | A named collection of ingested files under triage. Most extraction and search is scoped by `dataset_id`. Some graph nodes are dataset-agnostic (`dataset_id IS NULL`). |
| **file** | One ingested artifact. Carries `filetype`, `filetype_group`, `sha256`, `md5`, size, path/uri. Content-identical files share one `sha256`. |
| **filetype** | The specific type of a file: `pdf`, `docx`, `eml`, `jpg`, `mp3`, … |
| **filetype_group** | The broad class of a file: `document`, `email`, `image`, `audio`, … Used to scope search and breakdowns. In chunk search only `document` and `email` are valid (they're the groups that produce text chunks); the field is a free string at the `file` level. **Not** "content type". |
| **extracted text** | `ExtractedText` — the full plain-text of one file (`content`), one row per file, produced by `extract-text`. The source for both chunking and mention character offsets. |
| **OCR** | Transcribing text from pixels (image-based PDF pages, images). Two tiers: `extract-text` OCRs image-based PDF pages inline with xberg (EasyOCR, offline); the `ocr` enrichment re-reads them (and images) with the stronger `pyocr` analytic, merged into the file's **extracted text**. Provenance in `DocumentMetadata.ocr_pages` / `ocr_model` (`easyocr` or the pyocr model id). |
| **image-based page** | A PDF page whose text layer has fewer than `min_chars` (20) word characters -- a scan or photo of a page. Recorded per document as `DocumentMetadata.image_pages` at `extract-text` time, whatever OCR ran. The unit OCR operates on; pages with a real text layer keep xberg's text. Not "scanned PDF" (a PDF can mix both). |
| **CLIP tag filter** | OCR's opt-in pre-filter: zero-shot CLIP over stored image embeddings, queueing only images whose probability mass on text-bearing tags clears a threshold. |
| **enrichment** | A queued analysis pass over a dataset's files (`SELECTOR_EXTRACTION`, `ENTITY_EXTRACTION`, `RELATIONSHIP_EXTRACTION`, `EMBEDDING`, …). Idempotent and queue-guarded: re-running is a no-op unless reset. |
| **staged** | A dataset whose files are all loaded and typed, so per-`filetype_group` counts and sizes are fixed. `dataset.date_staged` marks the milestone (stamped on `load-files`). Staging is the boundary that separates ingestion from enrichment and the basis for time estimates. |
| **enrichment run** | `enrichment_run` — one row per enrichment workflow invocation: analytic, dataset, device, units processed, duration. Distinct from the queue-level `enrichment` rows; it is both an audit log and the calibration source for estimates. |
| **work unit** | The thing an enrichment's runtime scales linearly with (`image`, `text_file`, `llm_file`, `contact_file`, `message`). One `enrichment_run` records its unit kind and count. |
| **throughput rate** | Median `duration_seconds / unit_count` for one `(enrichment_type, device)`, derived from `enrichment_run` rows. A seeded default (`DEFAULT_RATES`) stands in until ≥5 real runs exist, then the measured rate takes over. Drives `GET /datasets/{id}/enrichment-estimates`. |
| **analytic** / **analytics service** | An independently-deployable model service under `analytics/` (`clir`, `filetyper`, `pyparse`, `setfitcv`, `face`, `pyselectors`, `pyprompt`, `nerd`, …). Stateless, called in-process or over HTTP by orchestration. |
| **datastore** | A pluggable persistence backend behind a repository interface (`cipher/datastores/base/*.py` ABCs). Postgres (pgvector) and Elasticsearch today; the interface is the contract, the backend is deployment config. |
| **triage** | The core analyst workflow: sorting an unknown corpus into known schemas so it can be searched and reasoned over. |

## Retrieval

| Term | Meaning |
|---|---|
| **chunk** / **text chunk** | `TextChunk` — a contiguous slice of a file's extracted text, embedded for search. The retrieval unit. `DocumentTextChunk` / `EmailTextChunk` extend it per `filetype_group`. Carries `start_offset`/`end_offset` into the file's extracted text. |
| **embedding** | A dense vector for semantic similarity. Exists for chunk text, images, faces, and entity names. |
| **keyword search** | Lexical full-text ranking over chunk text (BM25, or Postgres FTS depending on backend). Matches verbatim terms. |
| **semantic search** | k-NN over chunk embeddings. Matches meaning, not words. |
| **hybrid search** | Fused keyword + semantic ranking (RRF). The default when neither lexical nor semantic is clearly preferable. |
| **entity search** / **knowledge-graph search** | Retrieval filtered or expanded by the entity graph — "passages that mention entity X", "… or anyone X communicates with". |
| **graph RAG** | Retrieval that starts from a seed entity, expands across relationships (bounded depth/weight), then gathers the evidence passages for that expanded set. |
| **correspondence filters** | `sent_from` / `sent_to` / `participants` / `date_from` / `date_to` — who sent what to whom, when. Matched against email header mentions; a person matches through its resolved header name and the addresses it `has_selector`. Shared by chunk search and email counts. |
| **email counts** | `count_emails` — counts of distinct emails (deduped by `message_id`) matching correspondence filters, grouped by `sender` / `recipient` / `correspondent` or by `day` / `month` / `year`. Answers "who does X email the most". |
| **content date** | When a file's content was sent or authored: email `date_sent`, else document `date_content_created`. What `date_from`/`date_to` and browse ordering use — not `date_created` (ingest time). |
| **federated search** | One search interface spanning multiple `filetype_group`s / stores; a `filetype_group` filter scopes it, its absence searches all. |
| **retrieval backend** | The configured implementation of the chunk-retrieval interface (`postgres` \| `elasticsearch`). Selected by settings; both satisfy the same query contract. |

## Knowledge graph

| Term | Meaning |
|---|---|
| **entity** | A resolved thing in the knowledge graph. Supertype `entity` row + one typed detail table: `person`, `organization`, `location`, or `selector`. |
| **entity_type** | `person` \| `organization` \| `location` \| `selector`. (`device` is a schema/table but not an entity type.) |
| **selector** | An entity that is a strong identifier — phone, email, ip, passport, national_id, imei, imsi, iban, bank_card, social handle, crypto address, license plate. |
| **selector_type** | The broad selector class (12 members: `phone`, `email`, `ip`, …). First-class queryable column. |
| **selector_subtype** | The specific variant within a type (`telegram`, `btc_address`, `ru_inn`, `ir_code_melli`, …). First-class queryable column, `NULL` when the type has no meaningful subdivision. |
| **mention** | An evidence-anchored assertion that a span of a file fills one attribute of one entity. Carries offsets, `entity_attribute`, `extractor`, `provenance`, `extraction_confidence`, and (for selectors) `selector_type`/`selector_subtype`, `normalized_value`. |
| **entity_attribute** | Which attribute a mention fills: `person.name`, `selector.value`, `location.address`, `location.coordinate`, … |
| **mention provenance** | The evidence *class* of a mention, coarser than where its anchor is: `text` (NER over body), `email_header`, `metadata`, `image`, `pattern` (deterministic/regex). Computed, not stored raw. |
| **relationship** / **entity_relationship** | A typed edge between two entities: `communicates_with`, `emailed`, `has_selector`, `employed_by`, `member_of`, `appears_in_photo_with`, … Carries `weight`, `source`, `date_observed_start`/`end`. Undirected pairs use a canonical (sorted) id order. |
| **channel edge** | A directed, weighted relationship type for one recorded interaction channel: `emailed` (sender → recipient, weight = emails) today; `called` / `messaged` when those producers exist. Distinct from `communicates_with`, the symmetric channel-less "these two talk" relation (stated in text or asserted by an analyst). A reply is its own edge the other way. |
| **top connections** | Ranking a set of seed nodes' neighbours by summed edge `weight` (one direction for directed types like `emailed`), for any *rankable* relationship type — one whose ontology `RelationshipSpec.weight` says what it counts (`WEIGHTED_RELATIONSHIPS`; the agent tool's choices are generated from it). Seeds can be a person/org (expanded through `has_selector`) or bare selectors, so it works before resolution; `roll_up` merges a neighbour's selectors into their single owner. All-time totals — date-bounded counts are **email counts**. |
| **relationship source** | *How* an edge was derived (`selector_inference`, `manual`, …). Distinct from a mention's **provenance** — do not conflate the two fields. |
| **canonical entity** | An entity that other names resolve *into*: bridged to a `person` / `location` record, or analyst-made (`source=manual`). SQL: `is_canonical_entity()`. |
| **provisional entity** | A person / organization / location entity `resolve-entities` minted for a name group with no match — a real `entity` row holding that group's mentions, but not canonical. Settled by **merge** (fold into a canonical entity; its name becomes an alias), **promote** (make it canonical — a person gains a person record), or **not an entity** (delete). API: `Entity.is_provisional`; the Resolve queue hides provisional candidates unless `include_provisional_entities`. |
| **entity_match** | A candidate resolution (mention or provisional entity → canonical entity), scored and pending analyst review. |
| **ontology** | The registry: entity types and their allowed attributes / selector types, plus relationship types and their endpoint rules and roles. Catalogued in `docs/ontology.md` and the app docs page; source of truth is `cipher/schemas/graph/ontology.py`. |
| **person (curated)** | The `Person` table — analyst-curated identities (faces, manual identification). Distinct from an extracted `entity` of type `person`; the two are bridged by a shared id when `entity.person_id` is set. |
| **rejected face** ("not a face") | A `face` row the detector got wrong (a pet, a pattern), marked by `date_rejected`. `rejection_method` is `manual` (analyst) or `automatic` (within `DEFAULT_FACE_REJECT_SIMILARITY` of a manual one — manual rejections are the negative exemplars). Excluded from search, matching, clustering and co-occurrence; never assigned; reversible. |
| **name group** | In Review: one distinct unresolved name and every mention of it across all files, counted together. |
| **mark invalid** | Analyst verdict on an existing entity. *Not an entity* deletes it and its mentions (they don't return to Review); *wrong entity* deletes it and unresolves its mentions back to Review. `DELETE /entities/{id}?discardMentions=`. |

## Identifiers on a selector

| Term | Meaning |
|---|---|
| **raw_value** | The original text span as it appeared in the document. |
| **normalized_value** | The canonical form after normalization (e.g. E.164 for phone, lowercased email, compacted IBAN). What dedup and cross-file matching key on. |
| **region_hint** | An ISO-3166-1 alpha-2 country hint that steers selector normalization/validation. |
| **attributes** | A `dict[str, str]` of validator-derived facts on a selector (phone carrier/geo/timezone, IBAN bank code, crypto network, …). Stored JSONB. |
