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
| **archive extraction** | `archive_extraction` (`cipher extract-archives`): unpacks zip / tar (and compressed tar) into **archive members** and decodes compressed files. Runs before every file analytic. `docs/archive-extraction.md`. |
| **archive member** | A `file` whose `parent_id` is the archive it was found in. Its `path` is where it was found (`<archive path>/<member path>`, display only); its `uri` is where the **output store** keeps it. One row per sighting. |
| **encrypted** | `file.is_encrypted`: reading the file needs a password -- a password-protected PDF or Office file, an S/MIME- or PGP-encrypted email (its headers are still read; its body is an encrypted `smime.p7m` child) or `.p7m` / `.gpg` file, or an archive holding encrypted members (members a known password opens are stored decrypted and not flagged; ones none opens aren't stored). A PDF locked only against editing isn't encrypted. Analytics that can't read it record it skipped (`encrypted: needs a password to read`). Passwords come only from the archive passwords file. |
| **compression** | `file.compression`: the single-stream encoding a file was found in (gzip, bzip2, xz, zstd, lz4) with the as-found bytes' hashes. An encoding of one file, never a container: `report.csv.gz` is a csv, `logs.tar.gz` a tar. Once decoded the row's own hashes describe the content. |
| **dataset** | A named collection of ingested files under triage. Most extraction and search is scoped by `dataset_id`. Some graph nodes are dataset-agnostic (`dataset_id IS NULL`). |
| **dataset member** | A user with a `user_dataset_access` row for a dataset: they can see and work in it. Membership is all-or-nothing (no per-dataset roles) and is meant to be synced from an external entitlement source; admins set it by hand until then. |
| **dataset content** | What dataset access protects: files, extracted text, chunks / search, images, faces, mentions (they quote the text) and email counts, plus comments on a dataset, file or image. Readable only by dataset members and admins, and the chat agent reads only the datasets its conversation is scoped to. The entity graph (entities, relationships, events, persons, locations) is shared and **not** access-controlled. |
| **selected datasets** | The datasets a user is working in (`user.selected_dataset_ids`), shared by the Entities, Events, Search and Graph pages through the header picker. Kept on the user, not in the browser; the API returns only datasets that still exist and the user can access, and deleting a dataset removes it from everyone's selection. A deep link naming a dataset (`?datasetId=`) scopes that one view without changing the selection. |
| **discoverable dataset** | A dataset with `is_discoverable`: listed to non-members with a lock (`has_access = false`) so they know it exists, but they can't open, triage or search it. |
| **admin** | A user with `is_admin`: sees every dataset without membership, creates/edits/deletes datasets, and manages users and membership. In development, requests without an `X-User-Id` header run as the seeded **Dev Admin** (`dev-admin@cipher.local`). |
| **file** | One ingested artifact. Carries `filetype`, `filetype_group`, `sha256`, `md5`, size, path/uri. Content-identical files share one `sha256`. |
| **filetype** | The specific type of a file: `pdf`, `docx`, `eml`, `jpg`, `mp3`, … |
| **filetype_group** | The broad class of a file: `document`, `email`, `image`, `table`, `audio`, … Used to scope search and breakdowns. In chunk search only `document` and `email` are valid (they're the groups that produce text chunks); the field is a free string at the `file` level. **Not** "content type". |
| **extracted text** | `ExtractedText` — the full plain-text of one file (`content`), one row per file, produced by `extract-text`. The source for both chunking and mention character offsets. |
| **OCR** | Transcribing text from pixels (image-based PDF pages, images). The `ocr` enrichment reads them with pyvllm's `ocr` model (jina-ocr-v1), merged into the file's **extracted text** (`extractor=pyvllm`). EasyOCR inline in `extract-text` (`--ocr-backend easyocr`) is only the fallback for a machine without it. Provenance in `DocumentMetadata.ocr_pages` / `ocr_model` (`easyocr` or the model id). |
| **image-based page** | A PDF page whose text layer has fewer than `min_chars` (20) word characters -- a scan or photo of a page. Recorded per document as `DocumentMetadata.image_pages` at `extract-text` time, whatever OCR ran. The unit OCR operates on; pages with a real text layer keep xberg's text. Not "scanned PDF" (a PDF can mix both). |
| **CLIP tag filter** | OCR's **gate** for images (on by default): zero-shot CLIP over stored image embeddings; the probability mass on text-bearing tags is the image's `has_text` **tag score**, and only images at or above the threshold are queued. |
| **tags** / **negative tags** | Labels for training classifiers over an object's embedding. `tags` = "is this" (positive); `negative_tags` = "is explicitly not this" (a hard negative). A tag sits in at most one of the two; absent from both means unlabelled. These columns (on `image`, `file`, `entity`, `event`, mirrored onto `person` / `location`) are read copies of the **`tag`** rows. **Content** tags are keyed by `sha256`, so every copy of a file and its `image` row share them. Labelling one object never propagates to similar ones. |
| **tag score** | `file.tag_scores[tag]` / `image.tag_scores[tag]` — a model's confidence (0–1) that a tag applies. A prediction, not a label: it sits beside `tags` / `negative_tags` so the two can be compared, and an analyst accepting or rejecting it produces the label. |
| **tag filter** | A per-tag filter state: `tags` (labelled this), `negative_tags` (labelled not this), or `predicted_tags` (scored at least `min_tag_score` and not yet labelled). Each list matches any of its tags; the lists combine with AND. In the UI one click on a tag cycles tagged → not → predicted → off. |
| **from the data** | A fact that came with the files at export (a mail client's labels, a document's own properties), as opposed to a **tag**, which is a user's or a model's decision. Shown in a neutral colour (not amber) with where it came from, e.g. *Gmail · X-Gmail-Labels*. |
| **source tags** | `file.source_tags`: tags **from the data**, in a common vocabulary. Today these are an email client's inbox categories (`EmailCategory`: Gmail's `promotions`, `updates`, `social`, ...). The name is generic so that SMS / chat apps and document keywords can add to it later. Filter: `source_tags` / `exclude_source_tags` (any-of). |
| **message states** | `file.message_states`: every state a message's source recorded (`MessageState`: `spam`, `sent`, `archived`, `deleted`, `draft`, `flagged`, `starred`). Gmail labels can carry several. `EmailMetadata.state` keeps only the most definitive one. Filter: `message_states` / `exclude_message_states`. Both columns are copies of `extracted_text.metadata`, refreshed on every extraction upsert. |
| **quoted block** | `EmailMetadata.quoted_blocks`: an earlier message carried inside an email's **extracted text** -- reply history or a forward -- as character offsets, `kind` (`reply` / `forward`), its attribution as written and the quoted author (`from_name`, `from_address`) and `date_sent` when parseable. Found by `pyparse.parsers.email.quotes` from the localized attribution, separator, Outlook header or `>` lines; one block per quoted message. The email itself stays one **file**; a quoted message is not an email of its own. Entity extraction skips a block whose message the dataset also holds as its own email (`cipher.orchestration.quoted_copies`), so a thread's names count once; a quoted message with no file of its own is always extracted. |
| **conversation** | `EmailMetadata.conversation_id`: the thread an email belongs to -- the client's thread id (`X-GM-THRID`, the root of Outlook's `Thread-Index`), else the thread's root `Message-ID` from `References` / `In-Reply-To`. The email viewer also adds emails the headers miss when one quotes the other, with the same subject without Re: / Fwd:, within 30 days ("linked by quoted text"; `docs/conversations.md`). |
| **meaningful hash** | `EmailMetadata.meaningful_hash`: the same for every copy of one message, whatever mailbox it was found in (the recipient's inbox and the sender's Sent folder, two people on one server), where each copy's file `sha256` differs. `meaningful_hash_source` says how it was made: `message_id` -- from the `Message-ID` header; `content` (no Message-ID) -- from the sender's address, the To and Cc addresses, the send time to the second (UTC), the subject without `[EXTERNAL]`-style tags, and the body's first 2,000 letters and digits with links removed (Bcc is left out: only the sender's copy has it). `RE:` / `FW:` are kept, so a reply is a different message. The email view lists the other copies ("Same message as N other copies"). Chat messages use the same term for their own dedup hash. |
| **annotate** | Bulk labelling of one tag over the image grid: clicks stage positive / negative / unlabelled per image, then one save (`POST /images/annotate`) writes every change in a single transaction as the current user. |
| **`tag` (table)** | One source's decision about one tag on one target: `label` (positive / negative) and/or `score`, plus the source -- `user` (user id) or `model` (model name/version) -- and date. The latest label wins; clearing a tag removes every user's label for it (the UI confirms when that includes someone else's). Tags that predate provenance have source `unknown`. Written only through the tag repository, which keeps the tag columns in sync. |
| **gate** | A cheap first-pass model that decides which resources an expensive enrichment reads. Its score is the resource's **tag score**; below the threshold the enrichment is `SKIPPED`, except a small sample still processed so the gate's misses can be measured. First use: GLiNER in front of `extract-events --llm`. Also CLIP in front of `ocr` for images (`has_text`; an image under the threshold is left unqueued rather than `SKIPPED`). |
| **enrichment** | A queued analysis pass over a dataset's files (`SELECTOR_EXTRACTION`, `ENTITY_EXTRACTION`, `RELATIONSHIP_EXTRACTION`, `EMBEDDING`, …). Idempotent and queue-guarded: re-running is a no-op unless reset. |
| **output store** | Where Cipher writes files it creates itself (archive members, decoded files, email attachments): `<output uri>/<sha256[:2]>/<sha256[2:4]>/<sha256>`, written once however often the content is found. The **output uri** is a directory or `s3://bucket/prefix`, default `<OUTPUT_URI>/<dataset id>/`. Formerly "blob store". |
| **plan** (run plan) | Steps an admin queues on a dataset from the enrichment pipeline (staging and/or analytics, with their parameters), run by `cipher worker`. Rows of `enrichment_run` sharing a `plan_id`: **queued**, **running**, then **completed**, **failed**, **stopped** or **cancelled**. Users ask for work through GitHub issues instead. `docs/pipeline-runner.md`. |
| **pool** | The kind of host a plan step must run on: `cpu` or `gpu`. The LLM is not a pool: LLM steps run on a CPU host and call the LLM **service** over HTTP. |
| **service** | A shared server a step calls over HTTP (the LLM). Workers cap how many steps use one at once. |
| **staged** | A dataset whose files are all loaded and typed, so per-`filetype_group` counts and sizes are fixed. `dataset.date_staged` marks the milestone (stamped on `load-files`, which crawls a directory or `s3://bucket/prefix/` with include / exclude globs; the **staging** step of a plan). Staging is the boundary that separates ingestion from enrichment and the basis for time estimates. |
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
| **email counts** | `count_emails` — counts of distinct emails (deduped by **meaningful hash**, so a message found in several mailboxes counts once) matching correspondence filters, grouped by `sender` / `recipient` / `correspondent` or by `day` / `month` / `year`. Answers "who does X email the most". |
| **correspondent** | A name or entity named in an email's from / to / cc header (`field_path` `header.*`) — someone who sent or received the mail, not just someone it talks about. The Verify and Resolve queues list correspondents first, then by distinct files, then by mentions (`sort_by=evidence`). |
| **content date** | When a file's content was sent or authored: email `date_sent`, else document `date_content_created`. What `date_from`/`date_to` and browse ordering use — not `date_created` (ingest time). |
| **federated search** | One search interface spanning multiple `filetype_group`s / stores; a `filetype_group` filter scopes it, its absence searches all. |
| **search** (record) | A stored question: query + `dataset_ids` + scope, owned by a user, with an opaque id (`/search/[searchId]`). Never stores results — opening one re-runs it. Private to its owner (admins can read it). Unsaved ones are pruned after a short retention window; a **saved search** has `date_saved` and is kept. See `docs/global-search.md`. |
| **guided / auto** | How often the chat agent stops to ask the analyst (`autonomy`). **Guided** (the default): when a search for a broad question matches more than ~50 files, it asks how to go on before reading, and its other tools pause until the analyst answers. **Auto**: it asks only when two readings would give different answers. |
| **relevance judgment** | An analyst's relevant / not relevant mark on a source the chat agent cited. Sent with the next message so the agent builds on it or drops it; the relevant files can be tagged in one go. A (query, passage, label) triple like this is retrieval training data, but it is not stored yet. |
| **dataset profile** | The precomputed summary of a dataset (composition, content-date histogram, salient entities, correspondents) that the empty-query search briefing is built from. Recomputed after enrichment by `cipher profile-dataset`; it's dataset content, so it's access-gated. |
| **retrieval backend** | The configured implementation of the chunk-retrieval interface (`postgres` \| `elasticsearch`). Selected by settings; both satisfy the same query contract. |

## Knowledge graph

| Term | Meaning |
|---|---|
| **entity** | A resolved thing in the knowledge graph. Supertype `entity` row + one typed detail table: `person`, `organization`, `location`, or `selector`. |
| **entity_type** | `person` \| `organization` \| `location` \| `selector`. (`device` is a schema/table but not an entity type.) |
| **category** | Free-text kind of an organization (company, agency, division, office, branch) or location — same field name on both. Not an enum yet. |
| **location source** | `location.source` — where a point's coordinates came from. `name_mention`: a place *name* in text, located by the gazetteer (`resolve-locations`). `coordinate_mention`: a lat/long written in text (`extract-selectors`). Both are text mentions; the names mirror the mention's `entity_attribute` (`name` / `coordinate`). Also `exif`, `geocoded`, `device_gps`. The map shows **observed points** only: a gazetteer place (a `name_mention` row with no file — a city or country centroid) is its entity's detail, not a point. UI: *Place name in text*, *Coordinates in text*. |
| **parent organization** / **sub-unit** | `organization.parent_id`: the organization this one is part of. Mirrored as one `part_of` edge; an org has at most one parent. Sub-units are the orgs `part_of` it. Shown as the breadcrumb + **Structure** section on an organization page. |
| **selector** | An entity that is a strong identifier — phone, email, ip, passport, national_id, imei, imsi, iban, bank_card, social handle, crypto address, license plate, domain, MAC address. |
| **selector_type** | The broad selector class (14 members: `phone`, `email`, `ip`, … `mac_address`). First-class queryable column. |
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
| **rejected face** ("not a face") | A `face` row the detector got wrong (a pet, a pattern), marked by `date_rejected`. `rejection_method` is `manual` (analyst) or `automatic` (within `DEFAULT_FACE_SIMILARITY` of a manual one — manual rejections are the negative exemplars). Excluded from search, matching, clustering and co-occurrence; never assigned; reversible. |
| **name group** | Every still-unresolved mention of one name (by `normalized_value`) across all files, counted together — "dell": 639 mentions. The unit of the **Resolve** queue: one decision applies to all of its mentions. |
| **mark invalid** | Analyst verdict on an existing entity. *Not an entity* deletes it and its mentions (they don't return to the Resolve queue); *wrong entity* deletes it and unresolves its mentions back to the Resolve queue. `DELETE /entities/{id}?discardMentions=`. On an **event**: deletes it (`DELETE /events/{id}`, or many at once with `POST /events/mark-invalid`); re-extraction skips the file, so it does not return, and a file tagged `event` that is left with no events gets the tag moved to its negative tags. |
| **mention relationship** | A typed relationship between two **mentions** of one text, proposed by an extractor (the email-signature reader, an LLM pack, GLiNER) or drawn by an analyst (`extractor = manual`), before either end need be resolved. Pending until reviewed: *accept* (both ends resolved; it becomes a **relationship**, `source = manual`), *reject*, or *reopen*; `is_accepted` + `reviewed_by` record the decision. Never "link". |
| **email signature** | The block at the end of an email where the sender signs off with their name, title, organization chain, address and contact details. Read by `extract-signatures` into mentions (person, organization units broadest first, address and the city the gazetteer finds in it, phones / emails / website) plus **mention relationships** between them (`employed_by` with `role`, `part_of`, `located_in`), reviewed on the Entities page's *Email signatures* tab. Always "email signature", never bare "signature". |
| **twin mentions** | Two labels of one name in the same text from different extractors — the same span, or the same `normalized_value` on overlapping spans (`AAA Club Alliance Inc` / `AAA Club Alliance Inc.`). Shown as one chip; a relationship end resolves through its resolved twin. |
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
| **resolution unit** | Everything one name key covers: the unresolved mentions with that `normalized_value` and the person / organization entities whose name has it, whatever their type. `resolve-entities` decides once per unit -- `Adaire`, `Adaire's`, `Adaire (no reply)` and a person `Adaire` are one unit. |
| **short name in context** | A one-word person mention (`Nick`, `Mr. Bolton`) that `resolve-entities` resolves to the one fuller name in the same file it can stand for -- within-document coreference. |
| **patronymic** | A name part built from the father's given name (`Petrovich` ← Pyotr, `bin Khalid`). Two people whose patronymics differ are different people; a patronymic that names someone in the data becomes a `family_of` (parent) suggestion, a shared one a sibling suggestion. |
| **keep apart** | On a merge suggestion: say the auto-created entity is not the other one. Not suggested again. |
| **Verify tab** | Auto-created entities, biggest first, each with the entities it may duplicate (**merge** / **keep apart**). Check these before resolving more names to them. |
| **Resolve tab** | The queue of name groups. Each card shows suggested resolutions (accept / reject) and the other choices: another entity, create new entity, not an entity. |

## Identifiers on a selector

| Term | Meaning |
|---|---|
| **raw_value** | The original text span as it appeared in the document. |
| **normalized_value** | The canonical form after normalization (e.g. E.164 for a phone that states its country, lowercased email, compacted IBAN). A phone written without a country code keeps its national digits (`215.895.2372` → `2158952372`, `number_format = national`): a country is never guessed from the language, the sender's domain or an address. What dedup and cross-file matching key on. |
| **region_hint** | An ISO-3166-1 alpha-2 country hint that steers selector normalization/validation. |
| **attributes** | A `dict[str, str]` of validator-derived facts on a selector (phone carrier/geo/timezone, IBAN bank code, crypto network, …). Stored JSONB. |

## Tabular mapping

| Term | Meaning |
|---|---|
| **summary** | An LLM's 2–4 sentence description of one file, written on request (`cipher summarize`, or Summarize in the viewer) and stored as a **summary chunk** (`chunk.is_summary`; the flag also covers future generated whole-file descriptions like image captions) keyed by dataset + content hash, so identical files share it and search finds it. AI output, so shown in amber ("AI summary" on search hits). Never part of a file's text: spans, mentions and text reconstruction read `NOT is_summary` chunks only. |
| **table** | A file in the `table` filetype group (csv, tsv, xlsx, xls, xlsb, ods, parquet), identified by its `sha256` like an image; its page is `/tables/{sha256}`. |
| **table mapping** | `TableMapping` — how one sheet's columns map onto the ontology: column decisions, slots, edges. Shared by every file with the same **header fingerprint**. See `docs/tabular-mapping.md`. |
| **field type** | A column's type from pytabular's vocabulary (`person.full_name`, `selector.phone`, `location.latitude`, `edge.amount`, …), each pointing at an ontology attribute or selector type. |
| **detector** | One way of scoring columns against field types: `header`, `validators`, `gliner`, `nerd`, `llm`. Compared with `cipher eval-table-typing`. |
| **role** | Which party a column describes on a row (`sender`, `receiver`, `owner`, …), from leftover header words or the LLM. |
| **slot** | One entity per row built from a group of columns (`sender` = person[name, phone]). Edges connect slots. |
| **locked** | A column, slot or edge with `decision_source = user`: re-evaluation keeps it and re-runs everything around it. |
| **header layout** / **fingerprint** | A hash of a sheet's normalized header names. One `table_mapping` per (dataset, fingerprint); each file's sheets record theirs in `file.table_sheets`. |
| **emit** | Writing a verified table mapping's rows into the graph (`cipher emit-tables`): mentions, map points, edges. Re-emitting replaces the file's earlier output. |
