# Entities, Ontology & Knowledge Graph

How the entity layer fits into CIPHER: what it stores, how it connects to the
data already in the platform, and how it is built up during ingestion.

Status: **Phase 0 (skeleton) landed** — schema, tables, repositories, and the
`/entities` API. Extraction, resolution, and the agent tools follow in Phases
1–3 (see [Phasing](#phasing)).

**The full catalog of entity types, attributes, selector kinds, and relationship
types is in [`ontology.md`](./ontology.md)** (also rendered on the in‑app
`/docs` page). This document is the architecture; that one is the reference.

---

## 1. Why

CIPHER already resolves *people via faces* (`Person` / `Face` / `FaceMatch`) and
pulls *structured contacts* from vCards and email headers (`Contact`,
`NamedParticipant`). Nothing tied free‑text, EXIF, or structured evidence to a
single queryable notion of **entities and the relationships between them**.

The entity layer adds that: a small set of rich, typed entity tables — **Person,
Organization, Location, Selector** — plus **mentions** (where an entity appears
in evidence) and **relationships** (typed edges between entities), all built to
be driven by an ontology and queried by the chat agent.

---

## 2. The shape: one thin node + typed detail

Every entity is a row in **`entity`** (the graph node) plus a 1:1 row in a
**type‑specific detail table**:

```
entity(id, dataset_id, entity_type, display_name, display_name_normalized,
       aliases[], tags[], notes, source, is_verified,
       name_embedding vector(1024), person_id → person.id,
       location_id → location.id, date_*)

  ├─ person        (the EXISTING person table; entity.person_id bridges to it)
  ├─ organization  (entity_id, legal_name, aliases[], org_type, country, notes)
  ├─ location      (STANDALONE, bridged by shared id like person: entity.location_id,
  │                 location.id == entity.id. Also usable with no entity at all --
  │                 an EXIF photo point is just a location row with file_id set.
  │                 geom geometry(4326) NOT NULL, latitude, longitude, altitude,
  │                 geohash, name, category, address, city, admin_area, country,
  │                 tags[], attributes, file_id, dataset_id, source_id,
  │                 source ∈ named_mention|exif|geocoded|device_gps, date_recorded, ...
  │                 UNIQUE(file_id, source))
  └─ selector      (entity_id, dataset_id, selector_kind, raw_value,
                    normalized_value, region_hint)
                    UNIQUE(dataset_id, selector_kind, normalized_value)
```

Why a supertype node instead of independent tables:

- **One thing to point at.** `mention.entity_id`, `entity_relationship.src/dst_entity_id`,
  and `entity_match.entity_id` are all a single FK to `entity.id`. Graph
  traversal, cross‑type search, name‑embedding matching, and the review queue
  all operate uniformly on `entity`; you only join the detail table when you
  need type‑specific fields.
- **Person is untouched.** The FK lives on `entity.person_id` (nullable, unique),
  so `person`, `Face.person_id`, and `FaceMatch.person_id` need **no schema
  change**. A `person`‑type entity links to a `person` row; face evidence for an
  entity is reached through that bridge.
- **Location uses the same bridge.** `entity.location_id` (nullable, unique) and
  `location.id == entity.id`, so `location` is a standalone geospatial table that
  can also exist with no entity attached (a photo's EXIF GPS is just a `location`
  row with `file_id`/`image_id` set). The `/locations` map viewer reads this table.

Files:
`libs/cipher-schemas/src/cipher/schemas/{entity,organization,location,selector,mention,entity_relationship,entity_match,ontology}.py`,
`libs/cipher-datastores/src/cipher/datastores/postgres/tables/{entity,organization,location,selector,mention,entity_relationship,entity_relationship_candidate,entity_match}.py`.

---

## 3. Selectors are first‑class nodes

A **selector** is a strong typed identifier that resolves to one real‑world
thing: `phone`, `email`, `passport`, `national_id`, `imei`, `iban`, `handle`,
`crypto_address`, `license_plate`.

Modelling a selector as its own `entity` (not just a column on Person) is what
makes the shared‑identifier join work: one phone number seen across three
documents and two people is a single `selector` node with mentions in all three
files and `has_selector` edges to both people.

`(dataset_id, selector_kind, normalized_value)` is unique — that constraint **is**
the blocking key used by entity resolution.

### Email addresses connect senders and recipients

Email is a selector kind, and the pipeline uses it to wire up communication:

- For each participant on a message (`NamedParticipant{name, type, value}` from
  `EmailMetadata` / the eml parser), the pipeline emits:
  - a `structured_field` **mention** of the address (`field_path` = `"header.from"`,
    `"header.to[1]"`, …), and, when a name is present, a mention of the person;
  - a resolved/candidate **`email` selector** entity for the address;
  - a **`has_selector`** edge from the participant (person/org) to that selector.
- Between the sender and each recipient of the same message it emits a
  **`communicates_with`** edge. Endpoints are the resolved people/orgs when
  known, otherwise the bare `email` selectors — so sender↔recipient links exist
  even before names are resolved. (`COMMUNICATES_WITH` allows
  `person|organization|selector` on both ends; it is symmetric/undirected.)

The same pattern covers phone selectors from `Contact.phone_numbers`,
`Device.phone_numbers/imeis`, and mobile‑message dumps (`Message.sender/recipient`).

---

## 4. Mentions: attribute assertions grounded in evidence

**`mention`** is evidence that an entity has a particular attribute value:
`entity.<entity_attribute> = normalized_value` (seen as `surface_text`), for an
entity of `entity_type`, anchored at one span. A phone number → `selector.value`;
a name in prose → `person.name`; an address → `location.address`.

| field | meaning |
|---|---|
| `entity_id` | resolved entity — **null until resolution, and may stay null forever** |
| `entity_type` | predicted type |
| `entity_attribute` | which attribute this fills — `name` \| `alias` \| `address` \| `value` \| `date_of_birth` \| … |
| `normalized_value` | canonical attribute value (E.164, folded name, cleaned address); the resolution blocking key |
| `selector_kind` | selector `.type` when `entity_type` is `selector` |
| `surface_text` | the literal span text (`"Vladimir P."`, `"+7 495 …"`) |
| `mentioned_type` | `extracted_text` \| `image` \| `structured_field` |
| `provenance` | **derived, read-only** evidence class — `text` (NER/prose) \| `email_header` (`field_path` `header.*`) \| `metadata` (other `structured_field`) \| `image` \| `pattern` (`extractor='selectors'`). First match wins; see `mention_provenance()`. The dossier groups and filters on this, not on the raw span count. |
| `mentioned_id` | polymorphic pointer (no FK) — the `extracted_text.id` / `image.id` / `contact.id` / `device.id` |
| `file_id` | denormalized owning file, when applicable |
| `start_offset`, `end_offset` | **char offsets into `ExtractedText.content`** — the exact same contract `TextChunk` uses |
| `bounding_box` | normalized box for image mentions (same shape as `Face.bounding_box`) |
| `field_path` | dotted path for `structured_field` mentions |
| `context` | windowed snippet around the span, for display and agent grounding |

**Not every mention resolves.** `extract-entities` maps each extractor label to a
`MentionTarget` (`ontology.LABEL_TO_MENTION_TARGET`) carrying a
`ResolutionPolicy`: selectors resolve `by_value` (always); person/org names
`by_name_match` (attach to an existing entity, don't auto-create a bare one);
addresses `by_geocode` (only once coordinates exist); a bare
place/facility name is `manual_only` and stays an unresolved `location` mention
until a geolocation pass or an analyst promotes it. See `docs/ontology.md` §4.1.

Text offsets are into `ExtractedText.content`. If `extract-text` is re‑run with a
different extractor/version the offsets shift — mentions are tied to
`extracted_text` + `extractor` and are invalidated on change (same mechanism as
`reset-text`).

Faces are **not** copied into `mention`. The entity profile unions faces at read
time via `entity.person_id → face`; `mention` stays purely about NER + selector
extraction.

---

## 5. Relationships & the graph

Two tables, mirroring the `face` / `face_match` split:

- **`entity_relationship`** — a confirmed, asserted edge:
  `src_entity_id`, `dst_entity_id`, `relationship_type`, `directed`, `weight`,
  `source ∈ manual|extraction|selector_inference|co_mention|face_cooccurrence|import`,
  `attributes` (JSONB, e.g. a role title), `date_observed_start/end`.
  Unique on `(src, dst, relationship_type)`.
- **`entity_relationship_candidate`** — a proposed edge awaiting analyst review
  (`confidence`, `method`, `status`, `reviewed_*`). Confirming promotes it into
  `entity_relationship`.

Relationship types are registry‑defined (`schemas/ontology.py`), each with
allowed source/destination entity types:

| type | endpoints | notes |
|---|---|---|
| `has_selector` | person\|org → selector | an actor uses this identifier |
| `member_of`, `employed_by` | person → org | |
| `part_of`, `subsidiary_of` | org → org | **org sub‑units** (a regional office is itself an `organization` that is `part_of` the parent) |
| `located_in` | person\|org\|location → location | |
| `communicates_with` | person\|org\|selector ↔ same | symmetric; email/call/message links |
| `family_of`, `associate_of` | actor ↔ actor | symmetric; `associate_of` is co‑mention‑derived |
| `appears_in_photo_with` | person ↔ person | symmetric; two people whose faces are in the same image (either face may still be a *pending* match). `weight` = shared photos, `attributes.evidence` lists them (`verified`/`potential`). Two already-identified people are linked only once they share ≥ `--min-verified-photos` (default 2); a pair with a pending-match lead is linked from the first photo. Built by `link-face-cooccurrence`; excluded from default traversal |
| `same_as` | any ↔ any | asserted identity |
| `owns` | actor → any | |

**Traversal** (`PostgresGraphRepository`, implements the
`cipher.datastores.base.graph.GraphRepository` interface): breadth‑first with an
explicit visited set, capped at depth ≤ 3 and a server‑side `limit`, cycle‑safe.
`associate_of` (co‑mention) and `appears_in_photo_with` (face co‑occurrence) are
excluded from default traversal to keep multi‑hop answers useful. The
`GraphRepository` interface exists so a `Neo4jGraphRepository` can be swapped in
later without touching callers.

`appears_in_photo_with` edges are *derived*, never manually curated: they carry
`dataset_id = NULL` (a pair can share photos across datasets) and are fully
re‑reconciled from current `face` / `face_match` state on every run of
`link-face-cooccurrence`. The backend also reconciles the touched images inline
(`PostgresGraphRepository.recompute_face_cooccurrence_for_images`) whenever a
face is assigned, a `face_match` is confirmed/rejected, or a face is deleted — so
confirming an identity keeps the edge (now `verified`), and rejecting a match
prunes that photo and drops the edge once nothing supports it or it falls back
below the `min_verified_photos` floor. That floor (default 2, `1` disables it)
keeps a single shared photo between two already‑known people out of the graph
while always surfacing a pending‑match co‑occurrence as a lead; the inline hooks
use the default, so a non‑default `--min-verified-photos` run should be followed
by sticking with that value or re‑running the global rebuild.

### Batch face matching (`match-faces` / `face_matching` analytic)

Attaches loose faces to **known people**. The sweep counterpart to the reactive
matcher that already runs inline when an analyst adds a reference face
(`routes/persons._propose_potential_matches`) — same primitive
(`PostgresFaceRepository.get_potential_person_matches`), just not gated on a UI
action. **Person-level**: for each person's representative face(s) it KNN-searches
still-unassigned faces above `--similarity` and records a **pending `face_match`**
for analyst review — nothing is auto-assigned. O(representative faces) index
probes, not O(all faces). Idempotent (`face_match` is `ON CONFLICT DO NOTHING` on
`(face_id, person_id)`; only `person_id IS NULL` faces are candidates).
`--verified-only` restricts anchors to analyst-verified people. `match-faces
--reset` deletes the pending machine-proposed matches. Run it after
`detect-faces` and **before** `cluster-faces` (attach what belongs to known
people first, then cluster the genuine remainder) — `PIPELINE_ORDER` already puts
`face_matching` before `face_clustering`. Both `face_detection` and
`face_matching` are emitted by the "Face recognition" analytic on a dataset
request; like clustering, matching writes no per-face `enrichment` row.

### Face clustering (`cluster-faces` / `face_clustering` analytic)

Selectable on a dataset request as the **`face_clustering`** analytic
(`FaceClusteringParams`: `similarity`, `minImages`, `minFaces`, `k`,
`mergeIntoExisting`); executed by the `cluster-faces` sweep. It is not a
per‑face `enrichment` row — like `face_matching` it has no progress bar, only
the persons it produces.

Unsupervised identity discovery, so a drive of photos yields people without
seeding each by hand. A dataset‑wide sweep: `PostgresFaceRepository.knn_face_edges`
pulls a kNN similarity graph over **still‑unassigned** faces off the face HNSW
index (one correlated `LATERAL` query, not O(n²)), union‑find groups it, and each
cluster spanning ≥ `--min-images` distinct images (and ≥ `--min-faces` faces)
becomes one **unnamed, unverified** `person` (`source = face_clustering`) with
every face in it assigned (`assignment_method = automatic`) and the best‑quality
face set primary/representative. Smaller clusters and singletons stay unassigned.
Incremental — a re‑run only sees faces without a `person_id`; a new cluster near
an existing clustering person merges into it (`--no-merge` to always mint fresh),
and a cluster that brushes an analyst‑touched identity is left for review. Runs
`rebuild_face_cooccurrence` afterwards. Filter the results in the Persons UI with
`?source=face_clustering` / `?unnamed=true`; rename / merge / split there.
`POST /persons/{id}/merge` (`{ source_id }`) folds one person into another.
Everything keyed on the source's id or its shared‑id `entity` bridge repoints
onto `{id}`: `face`, `face_match`, `event_participant`, `comment` (person +
entity), `mention`, `entity_relationship` **and** the `entity_relationship_candidate`
/ `entity_match` review queues (self‑loops and rows that would duplicate one the
target already has are dropped, not repointed). Then the source person and its
entity bridge node are deleted; moved faces are stripped of their
representative/primary flags. The response reports a per‑table moved count.
`GET /persons/{id}/merge-candidates` ranks other persons by the strongest
representative‑face similarity to `{id}` — the "did you mean to merge these?"
shortlist the Persons UI shows in the merge dialog.
`cluster-faces --reset` drops the unverified `face_clustering` persons and unlinks
their faces.

---

## 6. Resolution: mentions → entities

`resolve-entities` is a **sweep job** (not a per‑file enrichment — it needs a
global view for blocking). For each batch of unresolved mentions:

1. **Block** — selectors: exact `(dataset_id, selector_kind, normalized_value)`
   lookup. People/orgs: trigram candidates on `display_name_normalized` +
   (Phase 2) `name_embedding` kNN.
2. **Score** — blended: trigram + name‑embedding cosine + selector overlap +
   attribute agreement (dob/sex) + co‑mention prior.
3. **Decide** —
   - `≥ auto_threshold` → attach the mention to the entity (create the `entity`
     + detail row if none; selectors dedupe on the unique constraint);
   - `review_low ≤ score < auto` → an **`entity_match`** candidate (pending);
   - `< review_low` → a new *provisional* entity.
4. Emit `has_selector` edges (or candidates) where a person/org mention and a
   selector mention co‑occur in the same span window.

**`entity_match`** is "FaceMatch for text": `mention_id`,
`provisional_entity_id`, `entity_id` (canonical target), `similarity_score`,
`match_method ∈ selector_blocking|name_fuzzy|name_embedding|llm|manual`,
`status`. Confirming attaches the mention and, if `provisional_entity_id` is set,
merges that provisional entity into the canonical one via
`PostgresEntityRepository.merge_entities`, which shares its repointing logic
(`repositories/_merge.repoint_entity_references`) with the person merge: mentions,
relationship edges + candidates, `entity_match` rows, event participations and
comment threads all move onto the canonical id (colliding / self-referential rows
dropped), then the provisional node is deleted.

---

## 7. How it connects to what already exists

| existing thing | connection |
|---|---|
| **`Person` / `Face` / `FaceMatch`** | `entity.person_id` bridges a `person`‑type entity to its `person` row; faces are surfaced on the entity profile via that bridge. No schema change to these tables. |
| **`ExtractedText.content`** | text mentions store char offsets into it (same contract as `TextChunk.start/end_offset`); the extractor already anticipated "future entity extraction" as a consumer. |
| **`TextChunk` (Elasticsearch)** | Phase 2 denormalizes `entity_ids` + `selector_values` onto chunks so the agent can do "semantic search restricted to files mentioning entity X". |
| **Email `NamedParticipant` / `EmailMetadata`** | header participants become `email`/`phone` selector entities + `has_selector` + `communicates_with` edges (see §3). |
| **`Contact`, `Device`** | their `emails` / `phone_numbers` / `imeis` become `structured_field` mentions and selector entities; a person sharing a selector value shows up on the entity profile. |
| **`Image` EXIF GPS** | Phase 3: EXIF coordinates become `location` entities with `source = exif`, linked to the image. |
| **`Enrichment`** | new `EnrichmentType` members `selector_extraction`, `entity_extraction`, `relationship_extraction` gate the per‑file extraction stages; resolution is a separate sweep. |

---

## 8. Pipeline

```
load-files → extract-text → embed-text
          → extract-selectors      (SELECTOR_EXTRACTION enrichment, per file — pyselectors)
          → extract-entities --extractor llm|gliner|nerd   (ENTITY_EXTRACTION — NER → name/address
                                    mentions + mention_relationship rows for every relation reported
                                    between two of those spans)
          → resolve-entities       (sweep: blocking + scoring + auto-link / candidates; then promotes
                                    every mention_relationship whose endpoints both resolved into an
                                    entity_relationship_candidate, endpoint types validated)
          → [extract-relationships](email communicates_with edges — selector-only; independent)
```

**`extract-llm` — one call for entities + events.** `cipher extract-llm --tasks
entities,events [--docs]` runs the `pyprompt` **`extract`** pack once per email
(and, with `--docs`, document) file, writing `mention` / `mention_relationship`
**and** `event` rows from a single structured response and completing both the
`ENTITY_EXTRACTION` and `EVENT_EXTRACTION` enrichments together. It halves the
model calls versus running `extract-entities --extractor llm` and `extract-events
--llm` separately, and keeps the entity list and an event's participants
consistent (they come from the same pass). `--tasks` picks the sections
(`entities`, `events`, or both). It is **email/document-scoped** — entity
extraction over *all* file types, and the `gliner` / `nerd` engines, stay with
`extract-entities`. Follow with `resolve-entities` then `resolve-event-links`.

**Cost / scale.** LLM inference is the bottleneck, so any bulk LLM pass
(`extract-llm`, `extract-entities --extractor llm`, `extract-events --llm`) is an
overnight job at best and only with a fast served model. `extract-llm`
specifically:

- fires `--concurrency` (default 8) calls at once so the server can batch them —
  the single biggest throughput lever; running one-at-a-time wastes the model
  server;
- logs a rolling seconds/file + ETA and warns once the projection passes ~8 h;
- **refuses** a run over `--max-files` (default **15,000**) unless `--yes`. Do a
  bounded `--limit N` slice first, eyeball the results, then run the rest;
- **stops** early if a whole batch fails (server down / wrong model / schema
  drift) instead of burning the retry budget.

Model guidance: a standard ~7–30B instruct model (vLLM/TGI, or a GGUF via
llama.cpp) or a cloud model. Avoid tiny models like `gemma-3n-E2B` for bulk
work — it runs ~20–40× slower than a normal dense model of similar size under
vLLM (~95 tok/s on a 3090) and over-generates under the schema. Measured on
`rag`: **Mistral-Small-24B Q5_K_M via llama.cpp**, `--concurrency 4`, ~10–15 s
per substantive email (172 mentions / 67 relations / 6 events from 40 files in
~20 min, incl. some 90 s timeouts on long emails → raise
`PROMPT_REQUEST_TIMEOUT`). Rough rates for ~25k email files: 24B local +
concurrency ≈ 3–7 days (use `--yes`); a 7–8B model ≈ overnight; cloud
(flash-lite) ≈ 1–3 h; `gemma-3n-E2B` sequential ≈ never.

`mention_relationship` (`libs/.../tables/mention_relationship.py`) holds a relation
between two `mention` spans, asserted by the extractor **before** either resolves —
so it is not lost while resolution catches up. `resolve-entities` promotes it once
both endpoints carry an `entity_id`.

`reset-entities` mirrors `reset-text`: drops `mention` / `mention_relationship` /
non‑manual `entity` + detail / `entity_relationship*` / `entity_match` for a dataset
and clears the enrichment rows.

### Extraction services

Four pluggable extractors under `analytics/`, all following the standard
service pattern (`api/deps.py` lifespan + `api/main.py`) and all emitting the
shared **`cipher.schemas.graph.spans`** contract (`EntitySpan`, `RelationSpan`,
`SelectorSpan`) so the pipeline can swap them. `extract-entities` takes an
`--extractor` switch; only `llm` (pyprompt) is wired today, `pygliner` / `nerd`
land in Phase 2.

| service | model style | best at | key bits |
|---|---|---|---|
| **`analytics/pyselectors`** | deterministic (regex + checksums) | strong identifiers — `phone` (E.164), `email`, `iban` (mod‑97), `imei` (Luhn), MRZ passports; char offsets into the input | `POST /extract`; 6 tests pass |
| **`analytics/pyprompt`** | LLM + structured output (`openai` SDK, any OpenAI‑wire endpoint) | free‑text **event** extraction, nuanced relations, and any prompt‑expressible task; repo‑resident prompt packs + a custom‑prompt escape hatch | `POST /entities` · `/events` · `/run`. Same `LLM__*` env as chat. Offsets resolved server‑side by locating each surface string. `app.state.pyprompt_runner` |
| **`analytics/pygliner`** | zero‑shot (GLiNER2.5 joint entities + relations) | long‑tail / ad‑hoc entity types **and relations**, multilingual, no training data | `POST /infer` (entities) + `POST /extract` (joint `JointIE` pass; each relation's head/tail restricted to the entity labels `RELATIONSHIPS` permits). Labels from `ontology.default_ner_labels()` / `default_relation_labels()`. `GLINER_MODEL_DIR` → a local checkpoint (`~/models/gliner/gliner2.5-multi-v1`), loaded offline. `app.state.pygliner_model` |
| **`analytics/nerd`** | supervised / fine‑tuned (transformers token classification) | high‑precision **standard** types (person / organization / location / date …) where labelled data exists | `POST /infer`. `NERD_MODEL_DIR` → a HF id or a local `nerd-*` checkpoint. HF `entity_group` tags folded to ontology labels by `nerd.labels`. `app.state.nerd_model`. `src/nerd/data/` holds the training dataset processors (`train` extra). Ported from the standalone `nerd` repo |

`cipher.schemas.ontology` exposes `NER_LABEL_TO_TYPE`,
`NER_LABEL_TO_SELECTOR_KIND`, and `RELATION_LABEL_TO_TYPE` so a workflow can map
any extractor's labels back to an `EntityType` / `SelectorKind` /
`RelationshipType`.

- **`pyselectors`** not `selectors` — the latter shadows a stdlib module (same
  reason `pyparse` / `pyxberg` carry the prefix). **`pygliner`** wraps
  GLiNER2.5; **`nerd`** is the supervised counterpart.

---

## 9. API

Router `backend/src/cipher/api/routes/entities.py`, prefix `/entities`:

| method + path | purpose |
|---|---|
| `POST /entities` · `GET /entities` | create / list‑filter entity nodes |
| `GET /entities/search?dataset_id=&q=&selector=` | fast resolution (exact selector + trigram name) |
| `GET /entities/{id}` · `PATCH` · `DELETE` | single CRUD |
| `GET /entities/{id}/profile` | dossier: detail, selectors, `mention_counts` keyed by provenance, `file_count` (**the headline "Mentions" number — distinct files where the entity is named in document text**; header From/To/Cc are relationships, selector hits are selectors), related entities, linked faces. Each `selector_mentions[]` also carries `sent_count`/`received_count` (distinct files with this address in a From/Sender vs To/Cc/Bcc header) and `text_count`/`pattern_count` (NER vs deterministic body-text hits) — the person dossier turns these into links to the selector's page and to `/search?q=&scope=`. |
| `GET /entities/{id}/mentions?provenance=` | evidence spans mentioning the entity; the dossier passes `provenance=text` |
| `GET /entities/{id}/relationships` | depth‑1 confirmed edges |
| `GET /entities/{id}/graph?depth=&types=&direction=` | bounded traversal → `{nodes, edges}` |
| `POST /entities/{id}/relationships` | assert an edge (validated against the ontology's endpoint rules) |
| `GET /entities/matches` · `POST /entities/matches/{id}/resolve` | entity‑resolution review queue |
| `GET /entities/relationship-candidates` · `POST /entities/relationship-candidates/{id}/resolve` | relationship review queue |

---

## 10. Agent integration (Phase 1)

The chat agent (`backend/src/cipher/api/routes/chat.py`, pydantic‑ai) gains tools
so it can choose how to answer:

- `find_entity(name?, selector_value?, entity_type?)` — resolve a name/phone/email/passport/handle.
- `entity_profile(entity_id)` — the dossier.
- `entity_mentions(entity_id)` — specific cited spans (returns `ChatCitation`‑shaped dicts, so the existing citations card renders them).
- `related_entities(entity_id, relationship_type?, depth)` — graph traversal.
- `search_by_metadata(query, entity_id?, ...)` — semantic/keyword search, optionally scoped to files mentioning an entity.
- `read_file(file_id, start_offset?, end_offset?)` — open and read a file's extracted text.

The ontology catalog (`ontology.ontology_summary_for_llm()`) is injected into the
agent instructions so the model knows the available types and relationships.

---

## 11. Migrations

Alembic lives in `libs/cipher-datastores/` (`alembic.ini`, `migrations/`). Two
revisions:

- `0001_baseline` — the schema as it stood before the entity layer, plus the
  `vector` and `pg_trgm` extensions.
- `0002_entities` — the 8 entity‑layer tables and their indexes. Purely
  additive; no existing table is altered.

Both use `Base.metadata.create_all(..., tables=[...], checkfirst=True)`, so they
are safe no‑ops if `create_all` already ran (dev/CI still call `create_all`).

```
cd libs/cipher-datastores
export ALEMBIC_DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/cipher
alembic upgrade head           # fresh database
alembic stamp 0001_baseline    # an existing create_all database adopting migrations
alembic upgrade head           # ...then apply 0002
```

Rule going forward: **new tables → `create_all` is still fine; column or data
changes → write an Alembic revision.**

## 12. Extending the ontology

All in `libs/cipher-schemas/src/cipher/schemas/ontology.py`:

1. Add an `EntityType` / `SelectorKind` / `RelationshipType` enum member.
2. Add a `TypeSpec` / `RelationshipSpec` entry (labels, allowed selector kinds,
   allowed edge endpoints, LLM‑facing description).
3. Only if you want a new *structured* filter/sort column on a detail table:
   add it to the detail table + schema (an Alembic revision). Otherwise **no
   migration** — enums are stored as varchar (`native_enum=False`).

New relationship endpoint rules are enforced by `validate_relationship(...)`,
which the `POST /entities/{id}/relationships` route calls.

---

## Phasing

| phase | scope | status |
|---|---|---|
| **0** | ontology registry, entity/detail/mention/edge tables, repositories, `GraphRepository` interface, `/entities` API, Alembic baseline | **landed** |
| **1** | `analytics/selectors`, `extract-selectors`, `resolve-entities` (exact blocking), agent tools `find_entity` / `entity_profile` / `entity_mentions` / `read_file` | next |
| **1b** | `analytics/pyprompt` LLM prompt-runner (`entities` / `events` packs + `/run`), `extract-entities --extractor llm` → name/address mentions | **landed** — opt-in; needs an `LLM__*` config |
| **2** | `analytics/pygliner` (GLiNER) + `analytics/nerd` wired into `extract-entities` via `--extractor`, name trigram/embedding resolution, provisional entities + merge, ES `entities` index + `entity_ids` on chunks, review UI | |
| **3** | relationship extraction (co‑mention + `pygliner` `/extract` (GLiNER2.5 joint), or `pyprompt` LLM relations), org sub‑unit hierarchy, EXIF locations, frontend `features/entities/` | |
| **4** | migrate `Face`/`FaceMatch` FKs onto `entity` (optional), cross‑dataset `canonical_entity_id`, optional `Neo4jGraphRepository` | |
