# Entity Resolution

How CIPHER decides that a *mention* ("Nick Bolton", `+7 495 123 45 67`,
`nbolton@gmail.com`) is the same real-world thing as an existing **entity**, and
that two entities are the same thing as each other.

This is the design/decision document: the options at each stage, what each one
buys and costs, and the recommended build. The architecture of the entity layer
itself (nodes, detail tables, mentions, the graph) is in
[`entities.md`](./entities.md); the type/selector/relationship catalog is in
[`ontology.md`](./ontology.md).

Status: **R0–R4 landed.** `resolve-entities` runs the full
block → score → decide → emit pipeline (blocks via `entity_name_key` + `has_selector`
traversal + trigram, scores Fellegi–Sunter, auto-resolves on the one safe rule,
files **group-level `entity_match`** rows, else provisional or leaves for review),
and `GET /mentions/{id}/resolution` + the `explain_entity_resolution` agent tool
make every decision inspectable. **R5** (Splink weight calibration) and **R6**
(optional: `dedupe-entities`, message/contact producers, cross-dataset merges,
`--use-embeddings`) below are the plan. A per-group concurrency pass is the noted
scale-out for large mailboxes.

---

## 1. Scope

Two distinct problems, same review queue:

| problem | input | output |
|---|---|---|
| **Mention resolution** | an unresolved `mention` row (`entity_id IS NULL`) | `mention.entity_id` set, or an `entity_match` candidate, or a new provisional entity |
| **Entity deduplication** | two `entity` rows of the same type | a `SAME_AS` edge and/or a merge of one into the other |

Mention resolution is the hot path (runs on every ingest). Entity dedup is a
periodic cleanup that mostly matters once provisional entities accumulate or when
resolving **across datasets**.

**Design targets** (from the platform owner):

- Typical dataset: **10k–100k entities**, hundreds of thousands of mentions. Must
  stay usable up to **100k+ entities / millions of mentions**.
- Entities are **arbitrary PII**, not public figures. A name like "Nick Bolton"
  or "Олена Ковальчук" has never been seen by any pretrained model. This shapes
  every "should we use embeddings?" answer below.
- **Multilingual**: Latin, Cyrillic, Arabic, CJK, mixed-script. Transliteration
  and per-culture name structure (patronymics, double surnames, family-name-first)
  are first-class, not an afterthought.
- **Explainable**: every auto-resolve and every review-queue candidate must carry
  a human-readable reason with per-signal contributions.
- **Correctness over recall.** A wrong auto-merge is worse than a missed one; the
  fallback is always the review queue.

---

## 2. What already exists (the rails)

Nothing needs to be invented for storage, review, or merge — only for
*blocking + scoring*.

| component | file | state |
|---|---|---|
| `entity_match` table + repo + `GET /entities/matches` + `POST /entities/matches/{id}/resolve` | `schemas/graph/entity_match.py`, `datastores/.../repositories/entity_match.py`, `routes/entities.py` | **exists; no writer** — nothing constructs `EntityMatchCreate` outside tests |
| `EntityMatchMethod` enum: `selector_blocking \| name_fuzzy \| name_embedding \| llm \| manual` | `schemas/graph/entity_match.py` | exists |
| `entity.name_embedding vector(1024)` + HNSW cosine index + `set_name_embedding()` | `datastores/.../tables/entity.py`, `repositories/entity.py` | **exists; no writer** — nothing computes an embedding |
| `entity.display_name_normalized` + GIN `gin_trgm_ops` index; `search_by_name` (pg_trgm, floor 0.3); `find_by_normalized_name` (exact) | `repositories/entity.py` | exists |
| `normalize_name()` — NFKD, strip combining marks, casefold, collapse whitespace. **Latin diacritics only; Cyrillic/Han left intact.** | `datastores/postgres/utils.py` | exists |
| Selector blocking key: `(dataset_id, selector_type, normalized_value)` unique (+ a `dataset_id IS NULL` global partial-unique for analyst selectors) | `datastores/.../tables/selector.py` | exists |
| `link_header_selectors(dataset_id)` — name mention + selector mention sharing `(file_id, field_path, dataset_id)` → `has_selector` edge | `repositories/entity_relationship.py` | exists |
| `resolve_entities_workflow` — groups unresolved `name` mentions by `(entity_type, normalized_value)`, exact-matches to an existing entity, else creates a provisional entity for "trustworthy" groups, else leaves for review; then `link_header_selectors` + `promote_to_candidates` | `orchestration/resolve_entities.py` | exists |
| `guess_actor_type(name)` — regex person-vs-org heuristic (`_ORG_WORD_RE`, `_PERSON_RE`) | `schemas/graph/ontology.py` | exists |
| `repoint_entity_references()` — the robust shared merge (mentions, edges, candidates, matches, event participants, comments) | `repositories/_merge.py` | exists; used by person merge and `PostgresEntityRepository.merge_entities` |
| `entity_match.resolve_match._merge` — a **simplified** local merge (mentions + edge endpoints only) | `repositories/entity_match.py` | exists; **should call `repoint_entity_references` instead** |
| Face-match subsystem: single candidate primitive (`get_potential_person_matches`), `DEFAULT_FACE_MATCH_SIMILARITY = 0.61` module constant, pending `face_match` rows, sibling auto-reject on confirm, `delete_automatic_pending` for `--reset`, reactive + batch both calling the one primitive | `repositories/face.py`, `orchestration/match_faces.py`, `routes/persons.py` | **the template to mirror** |

---

## 3. The pipeline

```
extract-selectors / extract-entities  →  unresolved mention rows
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    │                  resolve-entities                  │
                    │                                                    │
        BLOCK ──► COMPARE ──► SCORE ──► DECIDE ──► EMIT ──────► EXPLAIN   │
   (candidate      (per-       (one     (auto /   (mention.     (store    │
    entities per    signal      number  review /  entity_id,    per-      │
    mention)        feature     per      new      entity_match, signal    │
                    values)     pair)    provis.)  edges)        reasons)  │
                    └────────────────────────────────────────────────────┘
                                              │
                              dedupe-entities (periodic, optional)
                          BLOCK ──► COMPARE ──► SCORE ──► SAME_AS / merge
```

Each stage below is an options menu. The recommended default is called out; the
config knob that switches it is named.

---

## 4. Blocking — candidate generation

Blocking answers "which of the 50k entities could this mention possibly be?" It
must be **high recall** (a missed candidate can never be recovered downstream)
and **cheap** (runs per mention). Every strategy produces a set of `(mention,
candidate_entity)` pairs; scoring narrows them.

| strategy | mechanism | recall for… | cost | verdict |
|---|---|---|---|---|
| **Exact selector key** | `(dataset_id, selector_type, normalized_value)` equality on `selector` rows, then `has_selector` edges to actors | shared email / phone / passport / handle | O(1) index probe | **always on.** Highest-precision signal in the system. This is the `nbolton@gmail.com → Nick Bolton` path. |
| **Exact folded name** | `display_name_normalized ==` (`find_by_normalized_name`) | same script, same spelling, ASCII-foldable diacritics | O(1) index probe | **always on.** Current behaviour. |
| **Transliterated key** | ICU `Any-Latin; NFD; strip marks; lower` → equality on a stored `entity_name_key` | `Олена Ковальчук` ↔ `Olena Kovalchuk`; `محمد` ↔ `mohammed` | one string transform + index probe | **always on.** Cheap, CPU, no model. The single biggest multilingual win. |
| **Phonetic key** | Double-Metaphone / NYSIIS on the *transliterated* form → equality on a stored key | `Smith`/`Smyth`, `Kovalchuk`/`Kowalczuk`, OCR/typo noise | pure-Python, microseconds | **always on.** Latin-only, so it rides on transliteration. Adds spelling-variant recall trigram misses. |
| **Sorted-token key** | tokens sorted, joined → key | `Bolton Nick` ↔ `Nick Bolton`; header `Last, First` | trivial | **always on.** Handles name-order noise without full parsing. |
| **Trigram similarity** | `similarity(display_name_normalized, q) ≥ 0.3` (GIN index) | fuzzy Latin/transliterated: partials, middle names, minor edits | GIN scan, tunable | **always on.** Current behaviour; the fuzzy backstop. |
| **Surname / patronymic-stripped key** | culture-aware parse → key on `given + primary-surname` (drop patronymic, maternal surname, particles) | `Владимир Владимирович Путин` ↔ `Vladimir Putin`; `José García Hernández` ↔ `José García` | pure-Python parse | **on when a culture is inferred** (see §7). |
| **Name-embedding kNN** | clir (Jina v5) vector of `display_name + aliases`, HNSW cosine top-k | semantic nicknames (`Bob`↔`Robert`), heavy word-order/format variance, cross-script *without* a transliteration table | GPU to embed every entity + query; 1024 floats/entity storage; index build; freshness tracking | **opt-in only** (`--use-embeddings`). See §4.1. |
| **Co-occurrence blocking** | entities sharing a file / email thread / conversation / existing edge with the mention's neighbours | disambiguation, not recall — narrows an already-large candidate set | join on `mention`/`entity_relationship` | **on as a scoring feature**, not a primary blocker. |

**Recommended default blocker** = exact selector ∪ exact name ∪ transliterated ∪
phonetic ∪ sorted-token ∪ trigram ∪ (patronymic-stripped when culture known).
All CPU, all index-backed, no model. Cap the union at ~50 candidates per mention,
deduped by `entity.id`.

### 4.1 Why name embeddings are *not* the default

The owner's instinct is right. Weighing it explicitly:

**What embeddings add** over the CPU stack above:
- Semantic nickname/hypocorism matching (`Bob`↔`Robert`, `Sasha`↔`Aleksandr`) —
  but a **nickname lookup table** (a few hundred entries per language) covers the
  common cases deterministically and explainably.
- Cross-script matching with no transliteration rule — but ICU `Any-Latin`
  already covers every script we care about.
- Robustness to gross format noise — but sorted-token + trigram + phonetic
  already absorb most of it.

**What embeddings cost**:
- **GPU**: every entity name embedded on create/update, every mention embedded at
  resolve time. clir is a shared GPU service; this adds load to it.
- **Storage**: 1024 × 4 bytes = 4 KB per entity, plus an HNSW index. At 100k
  entities that's ~400 MB of vectors + index — not fatal, but not free.
- **Latency**: the resolve sweep gains a GPU round-trip per mention batch.
- **Freshness**: a dirty-tracking mechanism (null the vector on rename, re-embed)
  — more moving parts.
- **Marginal gain on *this* problem**: the model has never seen these names.
  A name embedding of an unknown proper noun is close to a
  character/subword-shape embedding — which is exactly what trigram + phonetic
  already give you, cheaply and transparently.
- **Explainability tax**: "cosine 0.83" is not a reason a reviewer can act on;
  "shared phonetic key KFLTXK; trigram 0.71" is.

**Verdict**: ship the CPU stack. Keep `name_embedding` / `NAME_EMBEDDING` /
the HNSW index as the **opt-in escape hatch** (`resolve-entities --use-embeddings`)
for a future dataset where evaluation shows the CPU blocker missing real matches.
Do not wire an `embed-entities` enrichment into the default pipeline.

**Entity-level embeddings** (a vector of the whole dossier, not just the name)
are further out of scope: even heavier, and the dossier is mostly selectors and
counts that structured features compare better.

### 4.2 Scale / speed / reliability of the R1 blocker (as built)

- **Storage**: `entity_name_key` holds ~6–8 rows per person/org/location entity
  (a `(entity_id, key_type, key)` PK plus one covering `(key_type, key)` btree).
  100k entities → ~0.7M rows; 1M entities → ~8M rows (~500 MB with the index) —
  comfortably within a single Postgres instance. Selector entities are **not**
  keyed (they resolve by exact value), which on an email-heavy dataset like `rag`
  keeps thousands of rows out of the table.
- **Speed — keying**: `cipher.names.entity_keys` is pure-CPU, ~10 µs/entity, no
  I/O. `backfill-entity-name-keys` keyset-paginates and chunks inserts at 5k rows;
  100k entities is a few seconds, 1M ~a minute. Inline refresh on an entity write
  is one `DELETE` + one small `INSERT` in the same txn — negligible, and entity
  writes are not a hot path (extraction creates them in a sweep).
- **Speed — lookup**: `get_resolution_candidates` is 3–4 index-backed round trips
  (selector, exact name, `entity_name_key` probe, trigram), and the sweep runs it
  **once per distinct unresolved name**, not once per mention — so millions of
  mentions collapse to tens of thousands of lookups. The `entity_name_key` probe
  is a single `(key_type,key) IN (…~7 pairs…)` query on the covering index.
- **Reliability — hot keys**: the lookup drops any single `(key_type, key)` that
  matches more than `per_key_cap` entities (default 200) as non-discriminative, so
  a common surname (`li`, `kim`) or a short phonetic code never floods the
  candidate set — the name still blocks on its precise keys (`folded`,
  `translit`, `given_surname`). Low-selectivity keys (`surname`, `initials`) stay
  recall-only; `initials` is emitted only for 3+ token names.
- **Reliability — freshness & determinism**: keys are a pure function of
  `display_name + aliases`, versioned by `cipher.names.KEYS_VERSION`. They refresh
  inline on `create_entity` / `update_entity` (name or aliases changed) /
  `upsert_person_entity` / `merge_entities`, drop by `ON DELETE CASCADE`, and a
  `backfill-entity-name-keys` re-run heals any drift (e.g. after a `cipher-names`
  upgrade). The blocker is additive — R1 does **not** change `resolve-entities`
  output, so there is no behavioural regression risk until R3 opts in.

---

## 5. Comparison — per-signal features

For each `(mention, candidate)` pair, compute a fixed vector of features. Each
returns a **level** (an ordinal: `exact` / `strong` / `moderate` / `weak` /
`none` / `conflict`) — never a raw float — so the score is a sum of
interpretable steps and the explanation writes itself.

| feature | compares | positive when | negative (`conflict`) when | cost |
|---|---|---|---|---|
| `selector_overlap` | selectors the mention's file+field references vs. the candidate's `has_selector` edges | shares an email / phone / passport / handle | — (absence is just `none`) | join |
| `name_exact` | folded names | equal | — | O(1) |
| `name_translit` | transliterated folded names | equal after `Any-Latin` | — | string transform |
| `name_phonetic` | double-metaphone keys | equal | — | microseconds |
| `name_trigram` | pg_trgm similarity, banded | ≥ 0.85 strong, ≥ 0.55 moderate, ≥ 0.35 weak | — | GIN |
| `name_structure` | culture-aware `ParsedName` components (§7) | `given + primary surname` match; initial-vs-full given; dropped maternal surname; patronymic ignored | **different surname**; incompatible generational suffix | pure-Python |
| `name_embedding` *(opt-in)* | cosine over `name_embedding` | ≥ 0.88 strong, ≥ 0.80 moderate | — | GPU/HNSW |
| `attribute_agreement` | mention's employer (from an extractor `employed_by`/`member_of` edge) vs. the candidate's `employed_by`/`member_of` org; DOB / nationality when present | equal employer / DOB / nationality | **different DOB** | edge lookup (wired R3.1) |
| `co_mention_prior` | resolved name entities in the same **file** as the mention's group vs. the candidate's `entity_relationship` neighbours (low-signal types excluded) | ≥ 2 shared → strong, 1 → moderate | — | one scoped self-join + one edge query (wired R3.1) |
| `provenance_weight` | `mention.provenance` (`email_header` / `metadata` / `pattern` / `text` / `image`) | structured-field mention → higher prior trust | — | field read |
| `type_agreement` | `mention.entity_type` (or `guess_actor_type`) vs. `candidate.entity_type` | equal | **person vs organization mismatch** → candidate dropped entirely | field read |

`conflict` on `type_agreement` or `attribute_agreement` is a **hard veto** — the
pair is discarded regardless of name similarity. This is what stops
"Bank of America" merging into a person "America Bankston".

### 5.1 Where each metadata signal enters

| source | how it becomes a mention | feature it feeds | status |
|---|---|---|---|
| **Email `From`/`To`/`Cc` (address + display name)** | `extract-selectors`: the address → a resolved `selector` mention (`field_path=header.from`); the display name → an untyped `name` mention with the same `field_path` and `context=<address>` | `selector_overlap` (via `_colocated_selector_values` + `has_selector` traversal), `provenance_weight` = `email_header` | **wired (R3)** — see the worked example in §16 |
| **Contact / vCard (name + phone + email + `ORG`)** | `extract-contact-entities` sweep: a person `name` mention + email/phone `selector` mentions all under `field_path="contact.name"`; `Contact.organization` → an org `name` mention + a `member_of` `mention_relationship` | identical to email headers — `selector_overlap` via the shared `field_path`; `provenance_weight` = `email_header` (structured) | **wired** (not demoable on `rag` — 0 contacts) |
| **Message (`sender`/`recipient` phone)** | `extract-message-selectors` sweep: each `sender`/`recipient` → a resolved `phone` `selector` mention (`field_path="message.sender"` / `"message.recipient"`) | feeds the graph, not name resolution directly — once a contact/header resolves a person to one of those numbers (`has_selector`), the conversation is connected | **removed 2026-09-29** (messages paused) |
| **LLM found name↔org in a signature** | `extract-entities --extractor llm`: `person` + `organization` `mention` rows + a `mention_relationship` (`employed_by`/`member_of`) | promoted to `entity_relationship_candidate` once both resolve (**wired**); **now also disambiguates**: the sweep populates `co_mention_prior` (same-file resolved neighbours) + `attribute_agreement.employer` (from the extractor's `employed_by`/`member_of` edge) | **wired** |

The LLM extractor's `response_format` is now **enum-locked to the ontology
vocabulary** (`pyprompt.schemas.build_entity_output_model` → `Literal` label
fields → JSON-schema `enum`), so the model can only emit canonical `EntityType`
/ `RelationshipType` labels — no paraphrase to guess at or silently drop.

---

## 6. Scoring — turning features into one number

| model | how | pro | con | verdict |
|---|---|---|---|---|
| **Weighted-sum / rule ladder** | hand-assigned points per feature level; sum; thresholds | dead simple, fully transparent, no training data | weights are guesses; no principled calibration; hard to keep balanced as features grow | **starting point only** |
| **Fellegi–Sunter (probabilistic record linkage)** | per feature level, a *match weight* `log2(m/u)` where `m = P(level \| same)`, `u = P(level \| different)`; total = Σ weights = a log-odds; sigmoid → [0,1] | the **match-weight breakdown is the explanation** (this is Splink's "waterfall"); `u` can be term-frequency-adjusted so common names ("Mohammed", "김") count for less; weights are estimable from data | needs `m`/`u` estimates (bootstrap by hand, refine from review history) | **recommended.** Native implementation, ~200 lines. |
| **Splink** | Fellegi–Sunter, productionised: EM to learn `m`/`u` unsupervised, a comparison-template library, DuckDB/Spark backends, built-in TF adjustments and charts | best-in-class weight learning + explainability; DuckDB backend needs no cluster | it links two *flat record tables* in a batch — it does not do incremental "attach this one mention to a growing entity set"; can't natively use selector-edge blocking or graph priors; extra runtime dep | **offline only** — see §9 |
| **Supervised classifier** (LogReg / GBDT on the feature vector) | train on labelled `(mention, candidate, match?)` rows | best raw accuracy once labels exist; LogReg stays explainable (per-feature coefficients) | needs a labelled set; GBDT is a black box | **later**, trained on accumulated `entity_match` review decisions; only if F-S proves insufficient |

**Recommended**: a native **Fellegi–Sunter** scorer.

- `m`/`u` per feature level live in an `EntityResolutionConfig` (see §8) with
  conservative hand-set defaults and a documented meaning.
- `u` for name features is **term-frequency-adjusted** using
  `display_name_normalized` frequency in the `entity` table — a match on a rare
  surname is worth far more than a match on "Ali". This alone materially improves
  correctness and costs one `GROUP BY`.
- The per-feature `(level, weight, contribution)` triples are stored verbatim as
  the explanation (§9).
- Splink is used **offline** to re-estimate those `m`/`u` values from real
  review-queue outcomes (§10), then they're copied back into the config. Splink
  never runs in the sweep.

---

## 7. Multilingual name handling

The hard part, and where correctness is won or lost. Layered, each layer optional
and independently testable.

### 7.1 Normalization (always)

Unicode NFKC → strip format/control chars → fold case → collapse whitespace and
punctuation. Extends today's `normalize_name` (which only handles Latin
diacritics) without changing its callers.

### 7.2 Transliteration (always)

| option | pro | con |
|---|---|---|
| **ICU `Any-Latin` transform** (PyICU) | script-complete (Cyrillic, Arabic, Han, Devanagari, Greek, Hebrew…); the same ICU already used in the Elasticsearch analyzers; deterministic; fast | native dependency (`libicu` system lib + `PyICU` wheel) |
| `unidecode` (pure Python) | zero system deps, tiny | weak/lossy on Arabic and CJK; Han → Pinyin is inconsistent |
| per-script hand tables | full control | enormous maintenance surface |

**Recommended**: ICU with an `unidecode` fallback if PyICU is unavailable at
import (the fallback degrades transliteration recall, nothing breaks).

### 7.3 Phonetic keys (always, Latin/transliterated only)

Double-Metaphone (primary) + NYSIIS (secondary) via `jellyfish` (pure-Python,
~0 deps). Run **after** transliteration. Catches spelling variants and OCR noise
that trigram misses. Not meaningful for un-transliterated CJK.

### 7.4 Culture-aware parsing (when a culture is inferred)

`parse_name(raw, *, culture=None, script=None, region_hint=None) -> ParsedName`
with `{prefix, given[], middle[], surname[], patronymic, particles[], suffix,
generational, script, culture}`. A rule registry keyed by culture:

| culture | rules |
|---|---|
| **East Slavic** (ru/uk/be) | order `Surname Given Patronymic`; patronymic suffix table (`-ovich/-evich/-ich/-ovna/-evna/-inichna`); **gendered surname pairs** (`-ov`/`-ova`, `-sky`/`-skaya`, `-in`/`-ina`) treated as equal; match may ignore patronymic |
| **Hispanic** (es) | two surnames (paternal + maternal) glued by `de/del/la/los/y`; **match on the paternal surname**; a single-surname mention still matches |
| **Lusophone** (pt) | multiple surnames, particles `de/da/do/dos/e`; maternal-then-paternal order |
| **Arabic** (ar) | `bin/ibn/bint` nasab chain, `Abu/Umm` kunya, `al-/el-` article stripped; match on ism + father's name |
| **CJK / Korean / Vietnamese / Hungarian** | **family name first**; 2–4-char Han names; Korean romanization variants (`Lee`/`Yi`/`Rhee`, `Park`/`Bak`) |
| **Icelandic** | `-son`/`-dóttir` patronymic, no inherited surname → match on `given + patronymic` |
| **Germanic / Dutch** | particles `von/van/der/den/ter/zu` — lowercase, keep with surname for matching, drop for sort |
| **generic western** (default) | first token = given, last = surname, middle = middle/initials |

**Culture inference**, cheapest signal first: selector `region_hint` → message
`language` → dominant Unicode script → a small name-lexicon lookup → default
`generic western`. Inference is best-effort; a wrong guess degrades to
`name_structure = weak`, never a `conflict`.

### 7.5 Nickname / hypocorism table

A static per-language map (`Bob→Robert`, `Sasha→Aleksandr/Aleksandra`,
`Bill→William`, …), a few hundred entries. Deterministic, explainable, covers the
main case people reach for embeddings to solve.

### 7.6 Packaging

| option | pro | con |
|---|---|---|
| **New `libs/cipher-names` package** (`cipher.names`: `script`, `translit`, `phonetic`, `parse`, `compare`, `keys`, `nicknames`) | standalone, unit-testable, importable by datastores + orchestration; matches the repo's "each feature usable stand-alone" rule; **pure CPU, microseconds per name** — no reason for a network hop | one more workspace member |
| module inside `cipher-utils` | no new package | mixes a substantial domain concern into a grab-bag |
| its own `analytics/` enrichment service | isolates the ICU dep; independently deployable | absurd overhead — a service call per name for work that takes microseconds; adds a failure mode to the sweep |

**Recommended**: `libs/cipher-names`, imported directly. It is fast enough to run
inline in the resolve sweep and in `create_entity`.

**But** the *precomputation of blocking keys per entity* (translit key, phonetic
key, sorted-token key, patronymic-stripped key) is worth materializing:

- a narrow `entity_name_key(entity_id, key_type, key)` table, GIN/btree indexed,
  populated on `entity` insert/update and by a one-off backfill;
- refreshed by a lightweight **`ENTITY_NAME_KEYS` enrichment** (CPU, per-entity,
  fast) so progress is visible and re-runs are cheap — this is the "maybe its own
  enrichment" the owner floated, and yes, it earns its place *for the keys*, not
  for the parsing.

---

## 8. Decision policy — auto vs. review vs. provisional  *(as built, R3)*

Resolution runs **per unresolved name group** (`unresolved_name_groups` — all
`name` mentions of one `normalized_value`), not per mention: a common name is one
decision, not thousands. After `decide()` bands the ranked candidates:

```
top.band == AUTO   (score ≥ auto_threshold AND margin ≥ min_margin AND
                    _auto_eligible: 'selector' blocked AND selector_overlap==exact
                    AND no conflict)
   → attach every mention_id in the group to top.entity_id now;
     write ONE group-level entity_match(mention_id=NULL, normalized_value=…,
       mention_count=…, status=confirmed, explanation.band='auto') as the audit row
any candidate band == REVIEW  (review_low ≤ score < auto, or ≥ auto but thin margin)
   → write a pending group-level entity_match per REVIEW candidate (top 5), each
     carrying its full explanation. Confirming one bulk-attaches the whole group
     and auto-rejects the sibling rows.
nothing clears review_low
   → PROVISIONAL: a dataset-scoped provisional entity, only for a typed group that
     is "trustworthy" (a structured mention, or ≥ min_mentions) and create_provisional;
     else the group is left for the analyst (untyped header names always land here)
```

The group-level `entity_match` (`mention_id IS NULL`, `normalized_value` set,
partial-unique on `(dataset_id, normalized_value, entity_id)`) is migration
`0018`. The sweep is idempotent (`on_conflict_do_nothing` + reads only
`entity_id IS NULL`); `reset-entities` clears it via `delete_by_dataset_id`.
`resolve_match` gained the `elif row.normalized_value:` branch that bulk-attaches
via `attach_names`, and its provisional `_merge` now calls the shared
`fold_entity` (repoint + keep the provisional's name as a canonical alias, also on
its person record, + re-key). The repointer drops `entity_match` rows that would
collide on any of the three unique keys, so a merge never fails on a name group
that proposed both entities.

**Provisional candidates.** When a canonical candidate reaches the review band,
the sweep drops provisional candidates for that group and re-bands the rest
(`_drop_provisional_if_canonical`) -- the stub-vs-canonical question belongs to
`dedupe-entities`. The Resolve queue also hides provisional candidates unless
`include_provisional_entities`. Recommended order: `resolve-entities` →
`dedupe-entities` → settle **Possible duplicate entities** (merge / promote /
not an entity) → `resolve-entities` again, so the folded aliases send the
remaining spellings straight to the canonical entity.

### Sweep cost (as built)

Grouping collapses millions of mentions to **distinct unresolved names** — a
typical dataset has hundreds to low-thousands. Up front: one `GROUP BY` for
name-frequency, one self-join for header-colocated selectors, one batched
`entity_name_key` probe. Then a **prefilter** drops every group with *no* signal
(no `entity_name_key` hit, no colocated selector, no same-name entity) straight to
provisional/left without a candidate query — this is most one-off newsletter
senders in a large mailbox. Groups with signal do ~5 sequential index queries
each (`get_resolution_candidates` + candidate detail). At the medium-scale target
that's seconds; for a mailbox archive with several thousand *signal-bearing*
sender names, **`resolve-entities --concurrency N`** scores groups in parallel,
each on its own session — measured **~6× faster on `rag` at `N=8`** (150 s vs
900 s). A failed group is logged and skipped (re-run retries it) rather than
aborting the sweep.

### Configurability

`EntityResolutionConfig`, passed to the enrichment run and persisted on it:

| knob | default | meaning |
|---|---|---|
| `auto_threshold` | conservative (tuned so auto precision ≥ ~0.99 on the eval set) | score at/above which a match auto-resolves |
| `review_low` | lower | floor for surfacing a candidate at all |
| `min_margin` | non-trivial | required gap between #1 and #2 to auto-resolve (blocks ambiguous auto) |
| `auto_methods` | `{selector_blocking}` | which blocking methods are eligible for auto at all |
| `create_provisional` | `true` | mint provisional entities for unmatched trustworthy groups |
| `require_name_agreement_for_auto` | `true` | a selector-backed auto also needs a real name match (any `name_*` exact, or `name_structure`/`name_trigram` strong+) — blocks a bare same-surname match on a *shared family mailbox* from auto-resolving one relative onto another |
| `cross_dataset` | `false` | see §11 |
| `use_embeddings` | `false` | add name-embedding blocking + feature |
| `min_mentions` | 2 | trustworthiness floor for provisional creation |
| feature `m`/`u` tables | hand-set, Splink-refined | Fellegi–Sunter weights |

### Is any rule reliable enough to be *always* auto?

**Yes, exactly one**: an **exact selector match on a structured header/contact
field**, with `type_agreement = exact` and no `attribute_agreement = conflict`.
That is: the mention is `From: Nick Bolton <nbolton@gmail.com>` (or a vCard
field), the address is already a `has_selector` of a person entity, and nothing
contradicts it. This is precisely what `link_header_selectors` already does today
for edges; extending it to also set `mention.entity_id` is not a new risk.

Everything else — exact *name* match included (two real different people share a
name) — is configurable and defaults to the review queue. This asymmetry is
documented here and surfaced in the `explanation` (`auto_rule: "exact selector on
structured field"`).

### Mirror the face-match ergonomics

- One candidate primitive: `PostgresEntityRepository.get_resolution_candidates(
  mention, *, dataset_id, cross_dataset, use_embeddings, limit)` — the *only*
  place "a possible match" is defined, used by the sweep and by any future
  reactive/API matcher (as `get_potential_person_matches` is for faces).
- `resolve-entities --reset` deletes system-created `entity_match` rows and
  un-sets `mention.entity_id` where `entity_match.reviewed_by = "system"`
  (mirror `delete_automatic_pending`).
- Confirming an `entity_match` auto-rejects the mention's other pending
  candidates (already implemented in `resolve_match`).
- Fix `resolve_match._merge` to call `repoint_entity_references` (the robust
  shared merge) instead of its simplified inline copy.

---

## 9. Explainability

Add `explanation JSONB` (nullable) to `entity_match` (migration 0015):

```jsonc
{
  "score": 0.94,
  "band": "auto",                       // auto | review | provisional
  "auto_rule": "exact selector on structured field",   // when band=auto
  "blocking": ["selector_key", "translit_key", "trigram"],
  "candidates_considered": 3,
  "features": [
    {"name": "selector_overlap", "level": "exact",  "weight":  6.1, "contribution":  6.1,
     "detail": "shared email nbolton@gmail.com (header.from)"},
    {"name": "name_structure",   "level": "strong", "weight":  2.3, "contribution":  2.3,
     "detail": "given+surname match; patronymic ignored (east_slavic)"},
    {"name": "name_trigram",     "level": "moderate","weight":  0.8, "contribution":  0.8,
     "detail": "similarity 0.71"},
    {"name": "attribute_agreement","level": "none",  "weight":  0.0, "contribution":  0.0}
  ],
  "runner_up": {"entity_id": "…", "score": 0.41}
}
```

Surfaces:

- **Review queue** renders the feature list as a waterfall ("matched because…").
- **`GET /entities/mentions/{id}/resolution`** — returns candidates + explanations
  even for auto-resolved and left-unresolved mentions, so an analyst can ask "why
  did / didn't this resolve?"
- **`EntitySearchResult.match_reason`** (already exists on `/entities/search`) —
  enriched from the same feature list.
- **Agent tool `explain_entity_resolution(mention_id | entity_id)`** — follows the
  `agent/tools.py` docstring + `agent.tool()` pattern; returns citation-shaped
  dicts.
- Frontend (separate repo) — a "Resolution" tab on the mention/entity; not in
  this plan's scope beyond the API.

---

## 10. Splink — where it fits

**What Splink is**: a Python library for probabilistic record linkage
(Fellegi–Sunter). It learns `m`/`u` weights unsupervised via EM, ships a
comparison-template library (name, DOB, Jaro–Winkler, embedding array
comparisons), adjusts for term frequency (common names count less), runs on
DuckDB in-process or Spark, and produces match-weight waterfall charts and a
comparison viewer.

**Why it's well regarded**: the unsupervised weight learning and the built-in
explainability are genuinely good, and DuckDB means no cluster.

**Why it is not the online matcher here**:

- It links two *flat record tables* in a batch pass. Mention resolution is
  incremental — attach one mention to an ever-growing entity set — which Splink
  doesn't model.
- Its blocking is SQL predicates on the record tables; it can't use our
  selector-edge graph or co-mention priors as blocking or comparisons without
  flattening everything first.
- It's another runtime dependency in the ingest path.

**Where Splink earns its place**:

1. **Offline weight calibration.** The training rows already accumulate: every
   `entity_match` carries `explanation.features` (the per-feature *levels* at
   decision time — config-independent) and, after review, `status` +
   `decision_source`. `scripts/calibrate_resolution.py` (R5) reads
   `entity_match WHERE reviewed_by IS NOT NULL`, flattens each to
   `{feature: level, …, label}` (weight `analyst` labels above `sibling_auto`),
   and either estimates `m`/`u` natively (`m = P(level | confirmed)`,
   `u = P(level | rejected)`, Laplace-smoothed → `log2(m/u)`) or feeds the
   labeled pairs to Splink (DuckDB) for supervised training. It also re-scans the
   labeled scores for the `auto_threshold` / `review_low` cutoffs that hit the
   target precision, and re-fits `base_prior` per provenance. Output: a new
   `EntityResolutionConfig` JSON to diff against the hand-set defaults and adopt.
   Splink touches no production data path. **Analysts produce this data by
   working the grouped review queue** (`GET /entities/matches/groups` +
   `resolve-batch` + `name-group/dismiss`); ~200–500 reviewed groups across a
   couple of real datasets is enough for a first calibration (rarer feature
   levels keep the hand-set default until they have volume).
2. **Batch entity↔entity dedup** (`dedupe-entities`, optional). After mentions
   resolve, provisional/extraction entities of one type *are* a flat record table
   — Splink's sweet spot. Run Splink (DuckDB) over `entity` + aggregated
   attributes, emit pairwise `entity_match` rows (`mention_id = NULL`,
   `provisional_entity_id` set, `match_method = "splink"`) into the **same review
   queue**; confirm → existing merge path. This is the natural tool for
   cross-dataset dedup (§11).

**Dependency posture**: `splink` as an **optional / dev** dependency (a
`calibration` extra on `cipher-orchestration`), never imported by the backend or
the default sweep.

`EntityMatchMethod` gains `translit_exact`, `phonetic`, `name_structure`,
`splink` (enum stored as varchar — no migration for the values themselves).

---

## 11. Cross-dataset resolution

Today `entity` is dataset-scoped (v1); `person`/`selector`/`location` bridge
nodes are the dataset-agnostic exception. Cross-dataset mention resolution is
**harder**, for concrete reasons:

- the selector blocking key and `display_name_normalized` uniqueness are
  per-dataset;
- provisional entities would multiply across datasets;
- an auto-merge across datasets is a much higher-stakes claim.

**Recommended**: a `cross_dataset` config flag (default `false`).

- **`false`** (default): blocking is scoped to the dataset (plus the
  dataset-agnostic `person`/`selector` bridge nodes, which already span
  datasets — so "this mention is the known person Nick Bolton" works across
  datasets *via the person bridge* even in within-dataset mode).
- **`true`**: `get_resolution_candidates` also searches other datasets'
  entities and `dataset_id IS NULL` nodes. Cross-dataset matches are **never
  auto-resolved** — they always land in the review queue — and confirming one
  writes a `SAME_AS` edge rather than merging rows. Actual row merges across
  datasets are left to `dedupe-entities` (§10) with Splink, which is the right
  tool for that batch problem.

This keeps the cheap common case cheap and defers the genuinely hard case to a
batch job built for it.

---

## 12. Recommended architecture — what should exist

| # | component | where | notes |
|---|---|---|---|
| 1 | **`libs/cipher-names`** — `script`, `translit` (ICU + unidecode fallback), `phonetic` (jellyfish), `parse` (culture registry), `compare` (`compare_names → NameComparison`), `keys` (`blocking_keys`), `nicknames` | new workspace lib | pure CPU; table-driven tests with real multilingual pairs |
| 2 ✅ | **`entity_name_key`** table + `backfill-entity-name-keys` sweep + inline refresh | `cipher-datastores`, `cipher-orchestration` | materializes translit / phonetic / sorted-token / surname / given+surname keys; `(key_type,key)` btree; refreshed inline on every entity write, CASCADE on delete. *(Built as a CLI sweep, not an `EnrichableType` — entities aren't one; avoids touching the enrichment enum/endpoints.)* |
| 3 ✅ | **`EntityResolutionConfig`** schema (§8 knobs, incl. the `weights` m/u table + `base_prior`) | `cipher-schemas` (`graph/entity_resolution.py`) | `DEFAULT_RESOLUTION_CONFIG`; R3 overrides via CLI flags |
| 4 ✅ | **`get_resolution_candidates()`** — the one candidate primitive | `PostgresEntityRepository` | mirrors `get_potential_person_matches`; unions selector ∪ exact-name ∪ `entity_name_key` ∪ trigram → `ResolutionCandidate` with `blocked_by` set. Scoring fields filled by R2. |
| 5 ✅ | **Fellegi–Sunter scorer** — `score_candidate` / `decide` / `build_explanation` / `dominant_method`; 9 features (§5), provenance prior, TF-adjusted name weights, `conflict` veto | `cipher-orchestration/entity_resolution.py` | pure, no I/O; 10 fixture tests. R3 builds the `*ScoringInput`s and persists. |
| 6 ✅ | **`resolve_entities` rewrite** — block → score → decide → emit per §8; group-level `entity_match` (migration 0018); `EntityResolutionConfig` via new CLI flags (`--auto-threshold`, `--review-low`, `--min-margin`, `--allow-auto-name`, `--cross-dataset`); keeps `link_header_selectors` + `promote_to_candidates`; `--reset` via existing `reset-entities` | `orchestration/resolve_entities.py`, `cli.py` | first `entity_match` writer; sweep stays a sweep (one `GROUP BY` for name-df + one join for header-colocated selectors, up front) |
| 7 ✅ | **migrations** — `0015_entity_name_key` (R1) · `0017_entity_match_explanation` (R2) · `0018_entity_match_name_group` (R3: `normalized_value` + `mention_count` + partial-unique). New `EntityMatchMethod` values need no migration (column already 17-wide). | `cipher-datastores/migrations` | |
| 8 ✅ | **`entity_match.resolve_match`** → group-attach branch + `_merge` now calls `repoint_entity_references` | `repositories/entity_match.py` | done in R3 |
| 9 ✅ | **Explainability surfaces** — `GET /mentions/{id}/resolution` (`MentionResolution` + `EntityMatchRef`; `list_for_name_group`) covering the negative case; agent tool `explain_entity_resolution` (deferred; `ChatDeps.entity_matches` wired). *Remaining polish: a `resolution` badge on `Mention` list rows, richer `match_reason` on `/entities/search`.* | `backend` | §9 |
| 10 | **`scripts/calibrate_resolution.py`** — Splink (optional dep) over review history → `m`/`u` | `cipher-orchestration` `[calibration]` extra | §10.1 |
| 11 | *(optional)* **`dedupe-entities`** sweep — Splink entity↔entity → `entity_match` (`match_method="splink"`) | `cipher-orchestration` | §10.2; also the cross-dataset merge path |
| 12 | *(optional)* **message / contact mention producers** — `Contact` and `Message.sender/recipient` emit name + selector mentions sharing a synthetic `field_path` | `orchestration/extract_selectors.py` | makes "address → person" resolvable from a vCard with zero email headers |
| 13 | *(opt-in, may never ship)* **`embed-entities`** + name-embedding blocking/feature | `cipher-orchestration` | gated by `use_embeddings`; only if evaluation shows the CPU blocker missing real matches |

---

## 12.1 Frontend fit — the simple analyst workflow

The frontend (`/home/boltonn/cipher/frontend`, `features/entities/`) is a separate
repo; this is the contract it consumes. **R3 now populates the queue with
group-level `entity_match` rows** (`normalizedValue`, `mentionCount`,
`explanation` set; `mentionId` null). R4 adds the one new read.

**Endpoints**

| verb + path | state | used for |
|---|---|---|
| **`GET /entities/matches/groups?status=pending&datasetId=&sortBy=`** | ✅ | **the fast-triage queue** — `EntityMatchGroup{surface, mentionCount, fileCount, status, top: EntityMatch, alternatives: EntityMatch[]}`, one card per name group (not N flat rows). `sortBy=similarity_score` (default) or `date_created` (= by `mentionCount`). |
| `GET /entities/matches?status=pending&datasetId=` | ✅ | flat rows, if a view needs them |
| `POST /entities/matches/{id}/resolve` `{status, reviewedBy, reviewNote}` | ✅ | one Confirm (bulk-attaches the whole name group) / Reject; siblings of a Confirm get `decision_source=sibling_auto` |
| **`POST /entities/matches/resolve-batch`** `{reviewedBy, decisions:[{matchId, status, reviewNote?}]}` | ✅ | **many decisions in one transaction** — the bulk-annotation path (≤ 500/call) |
| **`POST /entities/matches/name-group/dismiss`** `{datasetId, normalizedValue, reviewedBy, note?}` | ✅ | **"none of these"** — rejects every pending candidate for a name; a captured negative for calibration |
| `GET /mentions/{id}/resolution` | ✅ R4 | the "why?" popover — `MentionResolution{…, candidates[]}` with the `explanation` waterfall; empty = nothing blocked / nothing cleared review |
| agent tool `explain_entity_resolution(mention_id)` | ✅ R4 | same data for the chat agent |

Every `entity_match` row now carries **`decision_source`** (`analyst` \| `sibling_auto` \| `reconcile` \| `system_auto`, null while pending) so weight calibration (R5) can weight a real analyst label above a derived one.

**The loop**

1. **Dataset → Review tab** (`mention-review-list.tsx`). One row per name group,
   with its **top candidate**: a confidence bar (`match.similarityScore`), the
   `mentionCount` it covers, and the one-line reason from `match.explanation` (→
   e.g. *"→ Nicholas Bolton · 0.94 · shared email nbolton@gmail.com; surname
   exact"*).
2. **Expand** → the ranked candidate rows (up to 5 `entity_match` rows for the
   group). Each renders `explanation.features` as a small **waterfall of chips** —
   `selector +6.1`, `name structure +2.3`, `trigram +0.8` — on the amber
   annotation surface (per the AI/ML colour convention). A `conflict` chip (e.g.
   *DOB 1980 vs 1975*) shows why a name-identical candidate was vetoed and dropped.
3. **Confirm** → `POST …/resolve {status:"confirmed"}` — the backend
   bulk-attaches **every** unresolved `name` mention of that value
   (`attach_names`), auto-rejects the group's sibling `entity_match` rows, and
   merges a provisional entity if one was attached. **Reject** →
   `{status:"rejected"}` leaves the group unresolved.
4. **Auto-resolved** matches (the one always-auto rule — exact selector on a
   structured header/contact field) never enter the queue; they're already
   attached. On the entity dossier they show a **`system` badge** with an **Undo**
   that flips the stored `entity_match` to `rejected` and detaches the mention.
5. **Provisional entities** (nothing cleared `review_low`) appear in the dataset
   entity list with a **`provisional` tag** and a "merge from Review" hint — the
   pattern the entities UI already uses for extraction entities without a person
   bridge.
6. **"Why?" anywhere a mention is shown** (`entity-mention-popover.tsx`): a small
   fetch to `GET /mentions/{id}/resolution` renders the same waterfall from
   `candidates[].explanation`, including the negative case — an empty
   `candidates` list → *"nothing blocked"* or *"no candidate cleared review"*.
   The chat agent calls `explain_entity_resolution` for the same answer.

**Delta**: additive. No new pages. The review queue grows a candidates sub-list
(confidence bar + feature chips), Confirm/Reject point at the existing
`/entities/matches` endpoints, one new popover fetch, shared `Pagination` reused.
`EntitySearchResult.match_reason` (already on `/entities/search`) gets the richer
one-liner for free. The legacy name-group queue (`/mentions/unresolved-names` +
`POST /mentions/resolve-names`) still works and reads `mention` rows directly —
it and the `entity_match` queue coexist; the frontend can migrate at its own
pace to the one that carries explanations.

---

## 13. Phasing

| phase | scope | unlocks |
|---|---|---|
| **R0** ✅ | `libs/cipher-names` (translit, phonetic, script, parse, compare, keys, nicknames) + tests | multilingual matching primitives, standalone |
| **R1** ✅ | `entity_name_key` table (migration 0015) + `backfill-entity-name-keys` sweep + inline refresh on entity writes; `get_resolution_candidates` blocking primitive + `ResolutionCandidate` schema | high-recall CPU blocking |
| **R2** ✅ | Fellegi–Sunter scorer (`cipher.orchestration.entity_resolution`) + 9 features + `EntityResolutionConfig`/`DEFAULT_RESOLUTION_CONFIG` + `entity_match.explanation` JSONB (migration 0017) + `ResolutionExplanation`/`FeatureLevel`/`ResolutionBand` schema | scored, explainable candidates (engine only) |
| **R3** ✅ | `resolve_entities` rewrite (block→score→decide→emit) + CLI config flags; group-level `entity_match` (migration 0018); `resolve_match` group-attach branch + shared-`_merge` fix; **first `entity_match` writer** | the review queue fills; auto-resolve on the one safe rule |
| **R4** ✅ | `GET /mentions/{id}/resolution` (`MentionResolution`/`EntityMatchRef`, negative case included) + agent tool `explain_entity_resolution` + `ChatDeps.entity_matches`. *Polish deferred: `resolution` badge on mention rows, `match_reason` enrichment.* | analyst + agent can interrogate any decision |
| **R5** | annotation surface ✅ (`GET /entities/matches/groups`, `POST …/resolve-batch`, `POST …/name-group/dismiss`, `entity_match.decision_source` — migration 0020) · then `scripts/calibrate_resolution.py` over the accumulated labels | fast bulk review → weights learned from real outcomes |
| **R6** *(optional)* | ~~message/contact producers~~ ✅ (`extract-contact-entities`; `extract-message-selectors` removed 2026-09-29, messages paused) · `dedupe-entities` (Splink), cross-dataset flag, `--use-embeddings` | entity dedup, cross-dataset, embedding escape hatch |

R0–R4 + R3.1 is a complete, inspectable pipeline with no GPU and no Splink at
runtime: block → score → decide → emit, group-level review queue with per-feature
explanations, contact/message/header/LLM-signature signals all feeding the
scorer, `--concurrency` for large mailboxes, the shared-mailbox auto guard, and
the LLM extractor's output locked to the ontology vocabulary.
R5 tunes the weights from real review history; R6 is opt-in reach.

---

## 14. Benefits & limitations

**Benefits**

- No GPU, no model service, no network hop in the default path — CPU + Postgres.
- Every decision carries a per-signal reason a reviewer or the agent can act on.
- Multilingual is designed in: transliteration + phonetic + per-culture structure,
  not bolted on.
- Correctness bias: exactly one always-auto rule; everything else defaults to
  review; hard vetoes on type/attribute conflict; term-frequency down-weighting
  of common names.
- Reuses the entire existing review/merge machinery (`entity_match`,
  `resolve_match`, `repoint_entity_references`).
- Splink used where it's actually strong (offline weight learning, batch dedup),
  not forced into an incremental role it doesn't fit.

**Limitations**

- Culture inference is heuristic; a wrong guess weakens (never breaks) name
  structure matching.
- Transliteration collides (`Ali`/`Aly`/`Aliy` → one key) — mitigated by TF
  down-weighting and by never auto-resolving on a name signal alone.
- No semantic nickname matching beyond the static table unless `use_embeddings`
  is turned on.
- `m`/`u` weights are hand-set until enough review history exists to calibrate.
- Cross-dataset row merges are deferred to the optional batch job.
- ICU (`PyICU`) is a native dependency; the `unidecode` fallback degrades
  quality if it's missing.

---

## 15. Use-case playbook

| dataset shape | what carries the resolution | config |
|---|---|---|
| **Email-heavy** (mailbox, `.pst`) | `selector_overlap` on `header.from/to/cc` dominates; `link_header_selectors` + the always-auto selector rule do most of the work | defaults; `auto_methods = {selector_blocking}` |
| **Document-heavy** (reports, PDFs) | prose names → `name_structure` + `name_trigram` + `phonetic`; few selectors; most matches go to review | lower `review_low`; `create_provisional = true` |
| **Mobile / chat dump** | phone selectors + handles dominate; add message/contact producers (R6) so senders resolve | R6 producers; defaults |
| **Multilingual / cross-border** | transliteration + per-culture parsing carry it; ensure `region_hint` / message `language` are populated upstream for culture inference | defaults; consider `use_embeddings` only after evaluating recall |
| **Small (<10k entities)** | trigram + exact + phonetic is plenty | defaults; skip `entity_name_key` materialization if the sweep is fast enough (compute keys inline) |
| **Large (100k+ / many datasets)** | materialized `entity_name_key` matters; run `dedupe-entities` periodically; enable `cross_dataset` for review-only cross links | R1 materialization on; R6 `dedupe-entities`; `cross_dataset = true` |

---

## 16. Verification

- **Unit**: `libs/cipher-names` table-driven tests — `Владимир Владимирович
  Путин` ↔ `Vladimir Putin`; `José García Hernández` ↔ `José García`; `محمد بن
  سلمان` ↔ `Mohammed bin Salman`; `习近平` ↔ `Xi Jinping`; `Björk
  Guðmundsdóttir` ↔ `Bjork Gudmundsdottir`; `Smith`/`Smyth`; `Bob`/`Robert`.
- **Scorer**: fixture `(mention, candidate)` pairs with expected band + dominant
  feature.
- **End-to-end**: build a labelled eval dataset (per `CLAUDE.md`: *"if you need
  to test with fake data always create a new dataset and name appropriately"*) —
  e.g. `er-eval-multilingual` — with known ground-truth mention→entity links;
  measure auto-resolve precision (target ≥ 0.99), review-queue recall, and
  candidate-generation recall (the ceiling).
- **Pipeline**: `load-files → extract-text → extract-selectors → extract-entities
  → resolve-entities` on the eval dataset; inspect `GET /entities/matches` and
  `GET /entities/mentions/{id}/resolution`.
- **Regression**: `resolve-entities` is re-runnable and `--reset` restores the
  pre-resolution state (only touches `entity_id IS NULL` mentions and
  `reviewed_by = "system"` matches).
- **Calibration** (R5): hold out a slice of review history; check Splink-learned
  weights improve auto precision / review recall vs. the hand-set defaults before
  copying them into the config.

### Worked example (`rag`, 2026-09-06)

`resolve-entities` over the `rag` mail archive (~5.9k distinct unresolved sender
names, ~15 min sweep). After the run:

| `entity_match` status | groups | name mentions | examples |
|---|---|---|---|
| **confirmed** (auto) | 19 | 12,593 | `medium daily digest` (5,665), `nick b` (3,423), `cathi bolton` (1,790), `edmond bolton` (475), `e. f. bolton`, `mom`, `e'lir` — header name → the person/org that `has_selector` its address; typos caught by `name_phonetic` |
| **pending** (review) | 43 | 66,996 | `nick bolton` (14,856 — three ~0.99 candidates Nick B / Edmond / Cathi, the *shared family mailbox* `bolton213@yahoo.com`), `nicholas bolton` (3,225), `ed bolton` (2,852) |
| **rejected** | 2 | 493 | losing candidates for a group that resolved elsewhere |

- **`_reconcile_resolved_name_groups`** (end of the sweep) closes group-level
  rows whose name group is now fully resolved — `confirmed` if the row points at
  the entity the mentions actually resolved to, else `rejected` — so an
  auto-resolved name doesn't linger in the queue across runs. (Bug found + fixed:
  `create_name_group_match` was `on_conflict_do_nothing`; now `…_do_update`,
  never touching an analyst decision.)
- Selector-node false candidates (a `no-reply@…` entity trigram-matching its own
  address) and whitespace/punctuation "names" are filtered before scoring.
- **Tuning note**: on a *shared family mailbox* a bare surname match (`mary bolton`
  next to `bolton213@yahoo.com`) can auto-resolve on `selector_overlap` +
  `name_structure:moderate`. The system-`confirmed` row is auditable and undoable
  (§12.1). **Fixed** by `require_name_agreement_for_auto` (default on): a
  selector-backed auto now also needs a real name match, so `mary bolton` next to
  `bolton213@yahoo.com` goes to review, not auto.
