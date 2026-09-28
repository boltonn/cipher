# CIPHER Ontology Reference

The complete, current catalog of **entity types**, their **attributes**,
**selector kinds**, and **relationship types**. This is the thing to review and
push back on.

Source of truth: `libs/cipher-schemas/src/cipher/schemas/ontology.py` plus the
detail schemas (`person.py`, `organization.py`, `location.py`, `selector.py`) and
`mention.py`. Everything below is generated from those; extend the registry and
this doc together.

> Naming note: three extractor packages under `analytics/`, all emitting
> `cipher.schemas.spans`. **`pyselectors`** (not `selectors` — stdlib clash) is
> deterministic. **`pygliner`** is zero-shot (GLiNER2.5 joint entities +
> relations). **`nerd`** is supervised/fine-tuned token classification for
> *standard* entity types, ported from the standalone `nerd` repo.
> `extract-entities --extractor {pygliner|nerd}`.

---

## 1. Entity types

Every entity is a thin `entity` node plus one 1:1 detail row. All four types
share the node attributes in §1.0; each adds the detail attributes in its
sub-section.

### 1.0 Shared node attributes (`entity` table)

| attribute | type | notes |
|---|---|---|
| `id` | str (uuid4) | |
| `dataset_id` | str → `dataset` | entities are per-dataset for now |
| `entity_type` | enum | `person` \| `organization` \| `location` \| `selector` |
| `display_name` | str(512) | primary human-readable label |
| `display_name_normalized` | str | diacritic/­case-folded, for trigram match |
| `aliases` | list[str] | alternate surface forms |
| `tags` | list[str] | free-form analyst tags |
| `notes` | str \| None | analyst notes |
| `source` | enum | `extraction` \| `manual` \| `import` \| `face_clustering` |
| `is_verified` | bool | an analyst confirmed this is a distinct entity |
| `name_embedding` | vector(1024) \| None | `clir` embedding of name + aliases, for fuzzy resolution |
| `person_id` | str → `person` \| None | bridge to the legacy person table (unique) |
| `date_created` / `date_updated` | datetime | |

### 1.1 `person`

Real-world individual of interest. Reuses the **existing `person` table**
(unchanged); the entity node bridges to it via `entity.person_id`.

| attribute | type | notes |
|---|---|---|
| `name` | str \| None | |
| `aliases` | list[str] | |
| `notes` | str \| None | |
| `tags` | list[str] | |
| `date_of_birth` | datetime \| None | |
| `sex` | enum \| None | `female` \| `male` |
| `is_verified` | bool | analyst-confirmed identity |
| `source` | enum | `manual` \| `face_clustering` |

Face evidence for a person entity is reached through the bridge
(`entity.person_id → face`), not copied onto the entity.

Allowed selector kinds: `phone`, `email`, `passport`, `national_id`, `handle`,
`iban`, `crypto_address`.

**Mention-fillable attributes** (`ontology.attributes_for(PERSON)`): `name`,
`alias`, `date_of_birth`, `nationality`. A `person` mention asserts one of these,
e.g. a name in prose → `person.name`.

### 1.2 `organization`

A company, agency, unit, or other named group. Sub-units (offices, subsidiaries)
are themselves `organization` entities linked with `part_of` / `subsidiary_of`.

| attribute | type | notes |
|---|---|---|
| `legal_name` | str \| None | registered name if known |
| `aliases` | list[str] | trade names, abbreviations |
| `org_type` | str \| None | e.g. `company`, `agency`, `ngo`, `unit` |
| `country` | str \| None | |
| `notes` | str \| None | |

Allowed selector kinds: `phone`, `email`, `iban`, `handle`.
**Mention-fillable attributes**: `name`, `alias`.

### 1.3 `location`

A place: an address, a named place, or a geolocation from text or EXIF.

| attribute | type | notes |
|---|---|---|
| `address_text` | str \| None | free-text address / place description |
| `latitude` | float \| None | −90..90 |
| `longitude` | float \| None | −180..180 |
| `geohash` | str(≤12) \| None | for coarse proximity matching |
| `source` | enum | `named_mention` \| `exif` \| `geocoded` \| `device_gps` |
| `precision_m` | float \| None | approx positional uncertainty (metres) |
| `country` | str \| None | |
| `admin_area` | str \| None | state / province / region |

**Mention-fillable attributes**: `name`, `address`. A bare place/facility name
(`location.name`) does **not** auto-create an entity — it stays an unresolved
mention until a geolocation pass or an analyst supplies coordinates
(`ResolutionPolicy.MANUAL_ONLY`). An `address` mention resolves once geocoded
(`BY_GEOCODE`).

### 1.4 `selector`

A strong typed identifier that resolves to one real-world thing. Modelled as its
own entity so it can carry mentions and edges (one phone shared across three
files is one node). `(dataset_id, selector_kind, normalized_value)` is unique —
this is the resolution blocking key.

| attribute | type | notes |
|---|---|---|
| `selector_kind` | enum | the selector's **`.type`** — see §2 |
| `raw_value` | str | as first seen |
| `normalized_value` | str | the selector's **`.value`** — canonical form (E.164 phone, lowercased email, compact IBAN…) |
| `region_hint` | str \| None | region used to normalize, e.g. phone country |

**Mention-fillable attribute**: `value`. A `selector` mention always resolves —
normalize the value, then create-or-attach on
`(dataset, selector_kind, normalized_value)` (`ResolutionPolicy.BY_VALUE`).

---

## 2. Selector kinds

| kind | normalized form | extracted by |
|---|---|---|
| `phone` | E.164 (`+441234…`) | `pyselectors` (`phonenumbers`) |
| `email` | lowercased, trimmed | `pyselectors` |
| `iban` | compact, mod-97 checked | `pyselectors` (`python-stdnum`) |
| `imei` | 15 digits, Luhn checked | `pyselectors` |
| `passport` | MRZ header token | `pyselectors` (best-effort) |
| `national_id` | country-specific | `pygliner` / `nerd` NER label (no deterministic rule yet) |
| `handle` | `@name` lowercased | `pygliner` / `nerd` NER label |
| `crypto_address` | as-is | *(not yet extracted)* |
| `license_plate` | uppercased, spaces stripped | *(not yet extracted)* |

---

## 3. Relationship types

Directed unless marked otherwise. `symmetric` edges are stored once and treated
as bidirectional.

| type | direction (inverse) | source → dest | symmetric | description |
|---|---|---|---|---|
| `has_selector` | directed (`selector_of`) | `person` `organization` → `selector` | no | An actor uses this selector (phone/email/passport/…). |
| `member_of` | directed (`has_member`) | `person` → `organization` | no | A person belongs to an organization. |
| `employed_by` | directed (`employs`) | `person` → `organization` | no | A person is employed by an organization. |
| `part_of` | directed (`has_part`) | `organization` → `organization` | no | A sub-unit (e.g. a regional office) is part of a parent org. |
| `subsidiary_of` | directed (`parent_of`) | `organization` → `organization` | no | An organization is a subsidiary of another. |
| `located_in` | directed (`contains`) | `person` `organization` `location` → `location` | no | An entity is located at / within a location. |
| `communicates_with` | undirected | `person` `organization` `selector` ↔ same | yes | Recorded communication (email, calls, messages). Endpoints are people/orgs when resolved, else the bare email/phone selector. |
| `family_of` | undirected | `person` ↔ `person` | yes | Two people are family. |
| `associate_of` | undirected | `person` `organization` ↔ same | yes | Associated, usually inferred from co-mention. **Excluded from default graph traversal.** |
| `same_as` | undirected | any ↔ any | yes | Two nodes asserted to be the same real-world thing. |
| `owns` | directed (`owned_by`) | `person` `organization` → any | no | An actor owns an asset, account, or other entity. |

Edge attributes (`entity_relationship` table): `directed`, `weight`, `source`
(`manual` \| `extraction` \| `selector_inference` \| `co_mention` \| `import`),
`attributes` (JSONB, e.g. a role title on `member_of`),
`date_observed_start` / `date_observed_end`.

Endpoint rules are enforced by `ontology.validate_relationship(...)`, called on
`POST /entities/{id}/relationships` and by the extraction workflows.

---

## 4. Mentions — attribute assertions

A `mention` is **evidence that some entity has a particular attribute value**:
`entity.<entity_attribute> = normalized_value` (seen as `surface_text`), for an
entity of `entity_type`, grounded at one span. Examples:

| surface form | asserts |
|---|---|
| `+1 555 0142` | `selector`(type `phone`) `.value` = `+15550142` |
| `Vladimir P.` | `person.name` = `vladimir p` |
| `12 Bexterna St, Lviv` | `location.address` = `12 Bexterna St, Lviv` |
| `the North Facility` | `location.name` = `the north facility` *(stays unresolved)* |

`entity_id` links the mention to a specific entity **once resolved**, which may
never happen. `normalized_value` is the canonical attribute value and the
resolution blocking key.

| field | type | notes |
|---|---|---|
| `entity_id` | str → `entity` \| None | null until resolution (may stay null) |
| `entity_type` | enum \| None | predicted type |
| `entity_attribute` | str \| None | which attribute this fills — `name` \| `alias` \| `address` \| `value` \| `date_of_birth` \| … (per §1) |
| `normalized_value` | str \| None | canonical attribute value (E.164, folded name, cleaned address) |
| `selector_kind` | enum \| None | selector `.type` when `entity_type` is `selector` |
| `surface_text` | str | the literal span text |
| `mentioned_type` | enum | `extracted_text` \| `image` \| `structured_field` |
| `mentioned_id` | str | polymorphic id of the evidence row (no FK) |
| `file_id` | str → `file` \| None | denormalized owning file |
| `start_offset` / `end_offset` | int \| None | char offsets into `ExtractedText.content` |
| `bounding_box` | JSONB \| None | normalized box for image mentions |
| `field_path` | str \| None | e.g. `header.from`, `contact.phoneNumbers[0]` |
| `context` | str \| None | windowed snippet for display / grounding |
| `extractor` / `extraction_model` / `extraction_confidence` | str / float | provenance |

### 4.1 Label → attribute → resolution

The `extract-entities` workflow maps each extractor label to a `MentionTarget`
(`ontology.LABEL_TO_MENTION_TARGET` / `mention_target(label)`) and stamps
`entity_type` + `entity_attribute` + `selector_kind` on the mention. The
`resolution` policy tells `resolve-entities` whether/how the mention becomes an
entity.

| label | → | attribute | resolution |
|---|---|---|---|
| `person` | `person` | `name` | `by_name_match` — attach to an existing person by fuzzy name; do **not** auto-create from a lone name |
| `organization` / `company` | `organization` | `name` | `by_name_match` |
| `location` / `facility` | `location` | `name` | `manual_only` — never auto-resolves; waits for geolocation or an analyst |
| `address` | `location` | `address` | `by_geocode` — resolves once coordinates are derived |
| `phone number` | `selector` (`phone`) | `value` | `by_value` — normalize, then create-or-attach on the unique value |
| `email address` | `selector` (`email`) | `value` | `by_value` |
| `passport number` | `selector` (`passport`) | `value` | `by_value` |
| `national id number` | `selector` (`national_id`) | `value` | `by_value` |
| `bank account number` | `selector` (`iban`) | `value` | `by_value` |
| `social media handle` | `selector` (`handle`) | `value` | `by_value` |

---

## 5. Extractor label sets

`pygliner` labels are passed at inference time; `nerd` emits its checkpoint's
tags folded by `nerd.labels.normalize_label` (e.g. `PER`→`person`,
`GPE`/`LOC`/`FAC`→`location`). Both map back to types with `NER_LABEL_TO_TYPE`
(+ `NER_LABEL_TO_SELECTOR_KIND`); `pygliner` relations map with
`RELATION_LABEL_TO_TYPE`.

**Entity labels** (`default_ner_labels()`): person, organization, company,
location, address, phone number, email address, passport number, national id
number, bank account number, social media handle.

**Relation labels** (`default_relation_labels()`): has phone or email, member of,
employed by, part of organization, subsidiary of, located in, communicates with,
family of, associate of, owns.

---

## 6. How to extend

In `libs/cipher-schemas/src/cipher/schemas/ontology.py`:

1. Add the enum member (`EntityType` / `SelectorKind` / `RelationshipType`).
2. Add the `TypeSpec` / `RelationshipSpec` entry (labels, allowed selector kinds,
   allowed edge endpoints, description).
3. For a new entity type, add its detail table + schema (an Alembic revision).
   For a new relationship or selector kind: **no migration** — enums are stored
   as varchar.
4. Add a zero-shot label + `NER_LABEL_TO_TYPE` / `RELATION_LABEL_TO_TYPE` entry
   if the model should extract it.
5. Update this document and the frontend docs page (`app/(app)/docs`).
