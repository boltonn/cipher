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
       name_embedding vector(1024), person_id → person.id, date_*)

  ├─ person        (the EXISTING person table; entity.person_id bridges to it)
  ├─ organization  (entity_id, legal_name, aliases[], org_type, country, notes)
  ├─ location      (entity_id, address_text, latitude, longitude, geohash,
  │                 source ∈ named_mention|exif|geocoded|device_gps, precision_m, ...)
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
  `source ∈ manual|extraction|selector_inference|co_mention|import`,
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
| `same_as` | any ↔ any | asserted identity |
| `owns` | actor → any | |

**Traversal** (`PostgresGraphRepository`, implements the
`cipher.datastores.base.graph.GraphRepository` interface): breadth‑first with an
explicit visited set, capped at depth ≤ 3 and a server‑side `limit`, cycle‑safe.
`associate_of` (co‑mention) is excluded from default traversal to keep multi‑hop
answers useful. The `GraphRepository` interface exists so a `Neo4jGraphRepository`
can be swapped in later without touching callers.

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
merges that provisional entity into the canonical one (its mentions and edges are
reassigned, then it is deleted).

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
          → [extract-entities]     (ENTITY_EXTRACTION — pygliner or nerd — Phase 2)
          → resolve-entities       (sweep: blocking + scoring + auto-link / candidates)
          → [extract-relationships](co-mention + pygliner /relations or LLM — Phase 3)
```

`reset-entities` mirrors `reset-text`: drops `mention` / non‑manual `entity` +
detail / `entity_relationship*` / `entity_match` for a dataset and clears the
enrichment rows.

### Extraction services

Three pluggable extractors under `analytics/`, all following the standard
service pattern (`api/deps.py` model lifespan + `api/main.py`) and all emitting
the shared **`cipher.schemas.spans`** contract (`EntitySpan`, `RelationSpan`,
`SelectorSpan`) so the pipeline can swap them. `extract-entities` takes an
`--extractor` switch (`pygliner` | `nerd`).

| service | model style | best at | key bits |
|---|---|---|---|
| **`analytics/pyselectors`** | deterministic (regex + checksums) | strong identifiers — `phone` (E.164), `email`, `iban` (mod‑97), `imei` (Luhn), MRZ passports; char offsets into the input | `POST /extract`; 6 tests pass |
| **`analytics/pygliner`** | zero‑shot (GLiNER + GLiREL) | long‑tail / ad‑hoc entity types **and relations**, multilingual, no training data | `POST /infer` (entities) + `POST /relations` (`relations` extra). Labels from `ontology.default_ner_labels()` / `default_relation_labels()`. `app.state.pygliner_model` |
| **`analytics/nerd`** | supervised / fine‑tuned (transformers token classification) | high‑precision **standard** types (person / organization / location / date …) where labelled data exists | `POST /infer`. `NERD_MODEL_DIR` → a HF id or a local `nerd-*` checkpoint. HF `entity_group` tags folded to ontology labels by `nerd.labels`. `app.state.nerd_model`. `src/nerd/data/` holds the training dataset processors (`train` extra). Ported from the standalone `nerd` repo |

`cipher.schemas.ontology` exposes `NER_LABEL_TO_TYPE`,
`NER_LABEL_TO_SELECTOR_KIND`, and `RELATION_LABEL_TO_TYPE` so a workflow can map
any extractor's labels back to an `EntityType` / `SelectorKind` /
`RelationshipType`.

- **`pyselectors`** not `selectors` — the latter shadows a stdlib module (same
  reason `pyparse` / `pyxberg` carry the prefix). **`pygliner`** wraps GLiNER +
  GLiREL; **`nerd`** is the supervised counterpart.

---

## 9. API

Router `backend/src/cipher/api/routes/entities.py`, prefix `/entities`:

| method + path | purpose |
|---|---|
| `POST /entities` · `GET /entities` | create / list‑filter entity nodes |
| `GET /entities/search?dataset_id=&q=&selector=` | fast resolution (exact selector + trigram name) |
| `GET /entities/{id}` · `PATCH` · `DELETE` | single CRUD |
| `GET /entities/{id}/profile` | dossier: detail, selectors, mention counts, related entities, linked faces |
| `GET /entities/{id}/mentions` | evidence spans mentioning the entity |
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
| **2** | `analytics/pygliner` (GLiNER) + `analytics/nerd` wired into `extract-entities` via `--extractor`, name trigram/embedding resolution, provisional entities + merge, ES `entities` index + `entity_ids` on chunks, review UI | |
| **3** | relationship extraction (co‑mention + `pygliner` `/relations` / GLiREL, optionally an LLM pass), org sub‑unit hierarchy, EXIF locations, frontend `features/entities/` | |
| **4** | migrate `Face`/`FaceMatch` FKs onto `entity` (optional), cross‑dataset `canonical_entity_id`, optional `Neo4jGraphRepository` | |
