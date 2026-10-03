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
(`"document"`, `"has_selector"`); the Postgres enum columns store the member
*name* (uppercase) because they use `Enum(native_enum=False)`.

This file is living. Add a term the first time it needs defending in review.

---

## Corpus & ingestion

| Term | Meaning |
|---|---|
| **dataset** | A named collection of ingested files under triage. Most extraction and search is scoped by `dataset_id`. Some graph nodes are dataset-agnostic (`dataset_id IS NULL`). |
| **dataset member** | A user with a `user_dataset_access` row for a dataset: they can see and work in it. Membership is all-or-nothing (no per-dataset roles) and is meant to be synced from an external entitlement source; admins set it by hand until then. |
| **dataset content** | What dataset access protects: files, extracted text, chunks / search, images, faces, mentions (they quote the text) and email counts, plus comments on a dataset, file or image. Readable only by dataset members and admins, and the chat agent reads only the datasets its conversation is scoped to. The entity graph (entities, relationships, events, persons, locations) is shared and **not** access-controlled. |
| **discoverable dataset** | A dataset with `is_discoverable`: listed to non-members with a lock (`has_access = false`) so they know it exists, but they can't open, triage or search it. |
| **admin** | A user with `is_admin`: sees every dataset without membership, creates/edits/deletes datasets, and manages users and membership. In development, requests without an `X-User-Id` header run as the seeded **Dev Admin** (`dev-admin@cipher.local`). |
| **file** | One ingested artifact. Carries `filetype`, `filetype_group`, `sha256`, `md5`, size, path/uri. Content-identical files share one `sha256`. |
| **filetype** | The specific type of a file: `pdf`, `docx`, `eml`, `jpg`, `mp3`, … |
| **filetype_group** | The broad class of a file: `document`, `email`, `image`, `audio`, … Used to scope search and breakdowns. In chunk search only `document` and `email` are valid (they're the groups that produce text chunks); the field is a free string at the `file` level. **Not** "content type". |
| **extracted text** | `ExtractedText` — the full plain-text of one file (`content`), one row per file, produced by `extract-text`. The source for both chunking and mention character offsets. |
| **OCR** | Transcribing text from pixels (image-based PDF pages, images). The `ocr` enrichment reads them with pyvllm's `ocr` model (jina-ocr-v1), merged into the file's **extracted text** (`extractor=pyvllm`). EasyOCR inline in `extract-text` (`--ocr-backend easyocr`) is only the fallback for a machine without it. Provenance in `DocumentMetadata.ocr_pages` / `ocr_model` (`easyocr` or the model id). |
| **image-based page** | A PDF page whose text layer has fewer than `min_chars` (20) word characters -- a scan or photo of a page. Recorded per document as `DocumentMetadata.image_pages` at `extract-text` time, whatever OCR ran. The unit OCR operates on; pages with a real text layer keep xberg's text. Not "scanned PDF" (a PDF can mix both). |
| **CLIP tag filter** | OCR's **gate** for images (on by default): zero-shot CLIP over stored image embeddings; the probability mass on text-bearing tags is the image's `has_text` **tag score**, and only images at or above the threshold are queued. |
| **tags** / **negative tags** | Labels for training classifiers over an object's embedding. `tags` = "is this" (positive); `negative_tags` = "is explicitly not this" (a hard negative). A tag sits in at most one of the two; absent from both means unlabelled. These columns (on `image`, `file`, `entity`, `event`, mirrored onto `person` / `location`) are read copies of the **`tag`** rows. **Content** tags are keyed by `sha256`, so every copy of a file and its `image` row share them. Labelling one object never propagates to similar ones. |
| **tag score** | `file.tag_scores[tag]` / `image.tag_scores[tag]` — a model's confidence (0–1) that a tag applies. A prediction, not a label: it sits beside `tags` / `negative_tags` so the two can be compared, and an analyst accepting or rejecting it produces the label. |
| **tag filter** | A per-tag filter state: `tags` (labelled this), `negative_tags` (labelled not this), or `predicted_tags` (scored at least `min_tag_score` and not yet labelled). Each list matches any of its tags; the lists combine with AND. In the UI one click on a tag cycles tagged → not → predicted → off. |
| **annotate** | Bulk labelling of one tag over the image grid: clicks stage positive / negative / unlabelled per image, then one save (`POST /images/annotate`) writes every change in a single transaction as the current user. |
| **`tag` (table)** | One source's decision about one tag on one target: `label` (positive / negative) and/or `score`, plus the source -- `user` (user id) or `model` (model name/version) -- and date. The latest label wins; clearing a tag removes every user's label for it (the UI confirms when that includes someone else's). Tags that predate provenance have source `unknown`. Written only through the tag repository, which keeps the tag columns in sync. |
| **gate** | A cheap first-pass model that decides which resources an expensive enrichment reads. Its score is the resource's **tag score**; below the threshold the enrichment is `SKIPPED`, except a small sample still processed so the gate's misses can be measured. First use: GLiNER in front of `extract-events --llm`. Also CLIP in front of `ocr` for images (`has_text`; an image under the threshold is left unqueued rather than `SKIPPED`). |
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
| **mention value filter** | `mention_values` / UI `?mentionValue=` — files with a mention of a `normalized_value`, resolved or not (an IP, a name group). File-level, so header mentions count; a typed name is also matched in its folded form. `mention_provenance` narrows where the hit counts — body text (`text`/`pattern`) vs `email_header` vs `metadata` — so "mentions Nick in the text" differs from **correspondence filters**' sender/recipient. The sibling of the entity filter for evidence that has no entity. |
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
| **category** | Free-text kind of an organization (company, agency, division, office, branch) or location — same field name on both. Not an enum yet. |
| **location source** | `location.source` — where a point's coordinates came from. `name_mention`: a place *name* in text, located by the gazetteer (`resolve-locations`). `coordinate_mention`: a lat/long written in text (`extract-selectors`). Both are text mentions; the names mirror the mention's `entity_attribute` (`name` / `coordinate`). Also `exif`, `geocoded`, `device_gps`. The map shows **observed points** only: a gazetteer place (a `name_mention` row with no file — a city or country centroid) is its entity's detail, not a point. UI: *Place name in text*, *Coordinates in text*. |
| **parent organization** / **sub-unit** | `organization.parent_id`: the organization this one is part of. Mirrored as one `part_of` edge; an org has at most one parent. Sub-units are the orgs `part_of` it. Shown as the breadcrumb + **Structure** section on an organization page. |
| **selector** | An entity that is a strong identifier — phone, email, ip, passport, national_id, imei, imsi, iban, bank_card, social handle, crypto address, license plate, domain. |
| **selector_type** | The broad selector class (13 members: `phone`, `email`, `ip`, …). First-class queryable column. |
| **domain** | A website as a selector: the registrable domain (`target.com`) a URL or bare domain reduces to. An organization `has_selector` its domain; a website is never a person/organization name. Shown as “Website” in the UI. |
| **selector_subtype** | The specific variant within a type (`telegram`, `btc_address`, `ru_inn`, `ir_code_melli`, …). First-class queryable column, `NULL` when the type has no meaningful subdivision. |
| **mention** | An evidence-anchored assertion that a span of a file fills one attribute of one entity. Carries offsets, `entity_attribute`, `extractor`, `provenance`, `extraction_confidence`, and (for selectors) `selector_type`/`selector_subtype`, `normalized_value`. |
| **entity_attribute** | Which attribute a mention fills: `person.name`, `selector.value`, `location.address`, `location.coordinate`, … |
| **mention provenance** | The evidence *class* of a mention, coarser than where its anchor is: `text` (NER over body), `email_header`, `metadata`, `image`, `pattern` (deterministic/regex). Computed, not stored raw. |
| **relationship** / **entity_relationship** | A typed edge between two entities: `emailed`, `has_selector`, `employed_by`, `member_of`, `appears_in_photo_with`, `co_mention_of` (same chunk; for co-occurrence graphs, no producer yet), … Carries `weight`, `source`, `date_observed_start`/`end`. Undirected pairs use a canonical (sorted) id order. |
| **participant_in** | The graph edge from a person/org to an **event** node. Not stored: the graph repository reads it from resolved `event_participant` rows (role, RSVP) at traversal time. Graph nodes are entities plus `event` (`GraphNodeType`). |
| **channel edge** | A directed, weighted relationship type for one recorded interaction channel: `emailed` (sender → recipient, weight = emails) today; `called` / `messaged` when those producers exist. A reply is its own edge the other way. |
| **top connections** | Ranking a set of seed nodes' neighbours by summed edge `weight` (one direction for directed types like `emailed`), for any *rankable* relationship type — one whose ontology `RelationshipSpec.weight` says what it counts (`WEIGHTED_RELATIONSHIPS`; the agent tool's choices are generated from it). Seeds can be a person/org (expanded through `has_selector`) or bare selectors, so it works before resolution; `roll_up` merges a neighbour's selectors into their single owner. All-time totals — date-bounded counts are **email counts**. |
| **relationship source** | *How* an edge was derived (`selector_inference`, `manual`, …). Distinct from a mention's **provenance** — do not conflate the two fields. |
| **canonical entity** | An entity that other names resolve *into*: bridged to a `person` / `location` record, or analyst-made (`source=manual`). SQL: `is_canonical_entity()`. |
| **provisional entity** / **auto-created entity** | A person / organization / location entity `resolve-entities` created for a name group with no match — a real `entity` row holding that group's mentions, but not canonical. Settled on the **Verify** tab by **verify** (keep it as canonical — API `promote`; a person gains a person record), **merge** (fold it into the canonical entity it duplicates; its name becomes an alias), or **mark invalid**. UI label: *auto-created*. API: `Entity.is_provisional`, list filter `provisional=true`. |
| **resolution** / **entity_match** | A proposal that a name group (or a provisional entity) *is* a given entity, scored by the resolver and pending until an analyst **accepts** or **rejects** it. Stored as `entity_match`; `match_method` says what proposed it (`name_exact`, `selector_blocking`, …, `assistant` for chat). |
| **ontology** | The registry: entity types and their allowed attributes / selector types, plus relationship types and their endpoint rules and roles. Catalogued in `docs/ontology.md` and the app docs page; source of truth is `cipher/schemas/graph/ontology.py`. |
| **person (curated)** | The `Person` table — analyst-curated identities (faces, manual identification). Distinct from an extracted `entity` of type `person`; the two are bridged by a shared id when `entity.person_id` is set. |
| **rejected face** ("not a face") | A `face` row the detector got wrong (a pet, a pattern), marked by `date_rejected`. `rejection_method` is `manual` (analyst) or `automatic` (within `DEFAULT_FACE_REJECT_SIMILARITY` of a manual one — manual rejections are the negative exemplars). Excluded from search, matching, clustering and co-occurrence; never assigned; reversible. |
| **name group** | Every still-unresolved mention of one name (by `normalized_value`) across all files, counted together — "dell": 639 mentions. The unit of the **Resolve** queue: one decision applies to all of its mentions. |
| **mark invalid** | Analyst verdict on an existing entity. *Not an entity* deletes it and its mentions (they don't return to the Resolve queue); *wrong entity* deletes it and unresolves its mentions back to the Resolve queue. `DELETE /entities/{id}?discardMentions=`. On an **event**: deletes it (`DELETE /events/{id}`, or many at once with `POST /events/mark-invalid`); re-extraction skips the file, so it does not return, and a file tagged `event` that is left with no events gets the tag moved to its negative tags. |
| **mentions corrected** | A text in which an analyst drew, relabelled (span / type), or deleted a mention: `extracted_text.is_mentions_corrected`, with `mentions_reviewed_by`. Its current mentions are retraining material; a relabelled mention becomes `extractor = manual`. Bulk verdicts (*not an entity*) do not set it. |

## Resolution workflow (Entities page)

Turning extracted names into entities, in the words the app uses. **Verify** first, then **Resolve**.

| Term | Meaning |
|---|---|
| **mention** | One occurrence of a name or identifier in a file — "Dell" in one email's From header. |
| **name group** | Every unresolved mention of one name, counted together — see above. |
| **entity** | The single record for the real thing (Dell the company) that mentions resolve to. |
| **resolve** | Decide which entity a name group refers to. Every mention in the group then points at that entity. |
| **accept** | Take a suggested **resolution**: the name group resolves to that entity. Other suggestions for the name are rejected. |
| **reject** | Say a suggested resolution is wrong. The name group stays unresolved for another decision. |
| **resolve to another entity** | Pick an existing entity the resolver didn't suggest. |
| **create new entity** | Make a new person / organization / location entity from the name group and resolve the group to it. |
| **alias** | A curated alternate name of an entity (Nicholas Bolton, Nick Bolton). Resolving a name group does **not** add it as an alias: typos ("Nick BI"), punctuation variants, a bare surname or "friend" resolve to Nick but aren't his names. Add aliases from the entity page's **Names in the evidence** list. |
| **names in the evidence** | Every name group resolved to an entity, with mention counts — how the evidence refers to it. The source aliases are picked from. |
| **not an entity** | Discard the name group (a newsletter slogan, a greeting). Its mentions are dismissed. |
| **verify** | On an **auto-created** entity: keep it as a real, canonical entity (API `promote`). Dismisses its possible-duplicate suggestions. |
| **merge** | Fold a duplicate entity (Dell Inc) into the one it repeats (Dell). Mentions, edges and resolutions move over; the duplicate's name becomes an alias. |
| **Verify tab** | Auto-created entities, biggest first, plus pending merge proposals. Check these before resolving more names to them. |
| **Resolve tab** | The queue of name groups. Each card shows suggested resolutions (accept / reject) and the other choices: another entity, create new entity, not an entity. |

## Identifiers on a selector

| Term | Meaning |
|---|---|
| **raw_value** | The original text span as it appeared in the document. |
| **normalized_value** | The canonical form after normalization (e.g. E.164 for phone, lowercased email, compacted IBAN). What dedup and cross-file matching key on. |
| **region_hint** | An ISO-3166-1 alpha-2 country hint that steers selector normalization/validation. |
| **attributes** | A `dict[str, str]` of validator-derived facts on a selector (phone carrier/geo/timezone, IBAN bank code, crypto network, …). Stored JSONB. |
