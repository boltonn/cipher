# Tabular mapping

**Status (2026-10-04):** built end to end.
- `cipher map-tables` profiles files and stores one mapping per header layout (`table_mapping`, migration 0043).
- `/tables` is where you review, edit and verify a mapping.
- `cipher emit-tables` writes verified mappings as mentions, map points and edges. Then run `resolve-entities`.
- Not built: a char-level classifier, cross-table joins on key columns, and an automatic runner (emit is a CLI step).

**Decision.** Spreadsheets and exports (csv/tsv, xlsx/xls/ods, parquet, json/jsonl) get a
**table mapping** per sheet: each column gets a **field type** that points into the ontology,
typed columns are grouped into per-row **slots** (an entity each), and **edges** between slots
become relationships. An analyst edits and verifies the mapping before anything is written.

## 1. What already existed

Cell-level detectors were already there. pytabular adds the layer between them and the graph.

| Need | Reused |
|---|---|
| validate a bare cell as phone/email/IBAN/IMEI/passport/plate/MAC/... | `pyselectors.resolve_cell` (added for this) |
| coordinates in a cell (decimal, DMS, hemispheres, pairs) | `pyselectors.parse_degrees` / `parse_coordinate_cell` (added) |
| words that name a selector column (`телефон`, `госномер`, `bssid`) | `pyselectors.cue_words` -- the pack context terms (added) |
| country / city / region names | `cipher.places.Gazetteer.candidates` |
| person names, scripts, nicknames | `cipher.names` (`fold`, `dominant_script`, `canonical_forms`), `guess_actor_type` |
| zero-shot column classification | pygliner `classify` |
| whole-cell NER | nerd `infer_batch` |
| enum-locked LLM output | pyprompt (new `columns` pack) |
| structured record → mentions | `extract_contact_entities` (template for emitting) |

Presidio's structured mode does the same thing (sample rows, run recognizers per column).
These pieces are already multilingual and tuned to this ontology.

**Rule: nothing selector-shaped lives in pytabular.** Patterns, validation and cue words for
selectors live in pyselectors, even for types pyselectors didn't cover before. This build added:
- passport numbers (context-gated)
- the `license_plate` and new `mac_address` packs
- a context-gated bare-digit phone pattern

Header matching takes each selector type's *strong* cue words (weight ≥ 0.2). Weak ones like
`subscriber` for an IMSI nudge a match in text but would decide a whole column.

## 2. Pipeline

open → sniff encoding/delimiter → sample (head + spread) → find header → profile columns →
detectors (cascade) → decide field types → pair coordinates → slots + edges → `TableMapping`
→ store per (dataset, layout) → review / verify → stream all rows → emit mentions, points and
edges → `resolve-entities`.

## 3. Reader (memory-safe)

- **csv/tsv.** BOM, then UTF-8, then charset-normalizer restricted to common legacy codepages
  (cp1251, koi8-r, cp1256, gb18030, …). The delimiter comes from `csv.Sniffer`, falling back to
  field-count consistency. Every cell is read as a string.
- **Sampling.** Files over 64 MB are sampled by seeking to random byte offsets. Smaller files
  get one streamed reservoir pass.
- **Excel.** python-calamine. One sheet is held in memory at a time, which Excel's row limit
  caps.
- **Parquet.** pyarrow: the first batch plus random row groups.
- **json/jsonl.** Streamed and flattened to `a.b` keys.
- **Measured.**
  - Profiling a 2 GB / 24.6M-row CSV: 2.7 s, 390 MB peak RSS.
  - Streaming every row (`iter_batches`, polars): 2.4 s, 690 MB anonymous memory. The rest of
    RSS is the memory-mapped file.
- **Header detection.**
  - Scores the first 20 rows by how label-like they are, uniqueness, lexicon hits and contrast
    with the rows below.
  - Handles title rows above the header, two-row headers (merged group cells) and no header
    (`column_N`).

## 4. Detectors

Each detector returns `{field_type: score}` per column, so any combination can be compared.

- **header.** Multilingual synonyms (`data/header_lexicon.json`: en/ru/uk/zh/ar/fa/fr/es).
  - Inflected tokens match (`отправителя` ~ `отправитель`), and synonyms in CJK headers match as
    substrings.
  - Leftover header words name the **role** (`Телефон отправителя` → phone, sender).
  - Text fields over numeric cells are discounted.
- **validators.** Share of sampled cells passing a per-field check, times that check's strength.
  - Checks: pyselectors, checksum-valid national ids, gazetteer, dates in any order, epoch,
    DMS/decimal coordinates, name/org/address heuristics, and gender, currency and direction
    lexicons.
  - Phones: picks the best region per column (kept as `transform.region_hint`).
  - The same check gives the **hit rate** and failing cells shown after a user picks a type.
- **gliner.** `header: X | values: a; b; c` classified against every field description
  (in-process or `PYTABULAR_GLINER_URL`).
- **nerd.** Share of cells that are one whole person/org/location span.
- **llm.** pyprompt `columns` pack on a pipe-table preview. Field types and verbs are
  enum-locked. It returns per-column roles and the row's relationships, and is the only
  detector that does the grouping itself.
- **Char-level classifier (Sherlock/Sato style).** Not built. It becomes worth training once
  `labels.yaml` holds enough real labelled columns. spaCy isn't proposed: nerd and GLiNER already
  cover multilingual NER.

## 5. Decision

1. `header` and `validators` always run.
2. Model detectors run in order, and only while some column is under `accept_threshold` (0.75).
3. The score is a weighted average over detectors with an opinion, plus a bonus when they agree.
4. A header claim for a **disprovable** field whose cells all fail validation is halved (a
   `phone` column of names).
5. Below `other_threshold` (0.3), a column is `other`.
6. Adjacent latitude/longitude columns are paired.

Every column keeps per-detector evidence.

## 6. Field vocabulary

`data/field_types.json` (data, so it's easy to extend) has 58 types across person, organization,
location (address parts, latitude/longitude/pair/grid), selectors, time, edge attributes, keys and
other. Each has a `use`: `entity` attribute (or part), `edge_time`, `edge_attribute`, `key`,
`text` or `ignore`.

`needs_ontology: true` marks targets the ontology lacks today: person age/gender, organization
registration number and geohash. They're typed and shown, but not emitted.
`person.occupation` is an **edge attribute**: it becomes `role` on `employed_by` / `member_of`,
because a person can hold several roles over time.

## 7. Slots and edges

- Columns are grouped by role.
- Person and organization fields make actor slots, and selectors attach to the role's actor. A
  role with only selectors becomes selector endpoints.
- Location fields make a location slot.
- Several name columns in one role split into several slots.
- Edges:
  - person → org `employed_by`
  - actor → location `located_in`
  - family roles `family_of`
  - between the sender and receiver roles, the LLM's verb if there is one. Otherwise a guess:
    `called` (duration), `paid` (amount), `messaged` (free text) or `interacted_with`.
- `called`, `messaged` and `paid` are ontology verbs: per-channel and directed, like `emailed`.
  `interacted_with` is still only proposed (`is_proposed_verb`), so it isn't emitted.
- The date column becomes `date_observed`. Role/occupation columns go only onto employment
  edges. Amount, duration, direction, count and category go onto the other edges.

## 8. Edit → re-evaluate → verify

- **Who decided.** Column decisions, slots and edges carry `decision_source` (`model` | `user`).
  User ones are **locked**.
- **Re-evaluation.** `propose(sample, locked=...)` keeps them and re-runs everything that
  depends on them. Example: retype a column as latitude and its neighbour becomes longitude,
  and both join a location slot. It runs on the sample, so feedback is instant.
- **Lifecycle.** proposed → edited → **verified** (`is_verified` + `verified_by`, from the session)
  → emitted.
  - Any edit clears verified.
  - Verifying again re-emits idempotently: delete the file's `extractor="tabular"` mentions and
    relationships, then recreate them. Entities that resolution created are left alone.
  - A model re-run never touches verified mappings. `map-tables --repropose` re-runs the detectors
    on unverified ones and keeps user-set parts.
- **Storage.** One `table_mapping` row per (dataset, header fingerprint), with the mapping, a
  300-row sample, `is_verified` and `verified_by`. One verify covers every file exported by the
  same system. Each file's sheet layouts (header rows, data start, encoding, fingerprint) live on
  `file.table_sheets`.

## 9. Emit (`cipher emit-tables`, `extract_tables.py`)

- **Streaming and dedupe.** Rows stream in batches. Identical slot records within a file
  collapse into one set of `structured_field` mentions:
  - `field_path = table.<sheet>.<slot>`, so `resolve-entities` links names to their selectors.
  - `extractor = "tabular"`.
  - `context` is "row N (+k more)".
- **Values.** Names are composed from their parts. DOB is ISO, nationality an ISO country code.
  Coordinates also become `location` points (`coordinate_mention`, `attributes.extractor = tabular`):
  one per dated row (`date_recorded` from the row's time column, `duration_seconds` from a
  `time.duration` column), so a call log or GPS export is a timeline; undated coordinates collapse
  into one point per distinct record with `attributes.rows`.
- **Selectors.** Values are validated by `resolve_cell`, and failing cells are counted, never
  emitted. Selector entities are bulk get-or-created.
- **Edges.**
  - **Comms verbs between selector endpoints** (`called`/`messaged`/`paid`/`emailed`) go straight
    onto `entity_relationship`, like `emailed`: `weight` = rows, plus the observed date span.
    Each file's share is kept in `attributes.by_file`.
  - **Every other edge** is one `mention_relationship` per distinct pair, carrying `rows`, the
    first/last date, the amount total and the role history. Resolution promotes it to a candidate.
- **Re-emit.** It first takes out what the file's sheet wrote before: mentions (their
  relationships cascade), points, and its `by_file` share of each edge. So weights never double.
  Verified on a test dataset.
- **Queue.** `EnrichmentType.TABLE_EXTRACTION`, keyed on the filetype list
  (csv/tsv/xlsx/xls/xlsb/ods/parquet/json/jsonl). Files whose layout isn't verified yet stay queued.
- **Resolution.** DOB and nationality from a name's own records feed `attribute_agreement`
  (`resolve_entities._record_attributes`) on both sides: the name group, and the candidate's
  attached records plus `person.date_of_birth`. A different DOB vetoes an automatic merge. A
  matching DOB counts as STRONG, but still goes to review: the only automatic rule is still an
  exact selector match.

## 10. Review UI (`/tables/[sha256]`)

**`table` is a filetype group**, like `image`. It covers csv, tsv, xlsx, xls, xlsb, ods and parquet
(filetyper registry, plus migration 0044 for files staged earlier). json/jsonl stay `document`.

**One page per table, keyed by content hash** (`/tables/{sha256}`, `?datasetId=` when the same
file is in several datasets). It isn't in the sidebar: you review one table at a time, reached
from the file viewer ("Open table") or the file page ("Table view").

The page is the table itself, using the `TabularViewer` look, with the mapping drawn on it:
- **Entity bands over the headers.** Each group of columns that makes one entity per row
  (`sender`, `receiver`, ...) is a band in that entity type's colour.
- **A type chip on every header**, in the mention-chip states:
  - dashed amber = a model proposal not yet verified
  - entity colour = set by you, or verified
  - ghost = `other`

  A thin bar under each header shows the fit rate.
- **Clicking a chip** opens the same kind of popover as mention review: a type search grouped
  by entity, the amber "Detected" evidence per detector, the fit rate with failing cells, and
  the role. The role is what moves a column into another entity.
- **The toolbar** holds the relationship chips (`sender → Paid → receiver`; click to change the
  verb or switch it off; "+ Relationship"), "N files share this layout" (hover lists them,
  linking to their tables) and Verify.

API: `GET /tables/{sha256}`, `PUT /tables/mappings/{id}`, `POST /tables/mappings/{id}/verify`,
`GET /tables/field-types`, `GET /tables/verbs` (plus `GET /tables/mappings` for a dataset-wide
list). `PUT` re-evaluates on the stored sample with header + validators only, so no model runs
in the request path.

## 11. Use

```bash
cipher map-tables --dataset-name <name>                    # propose a mapping per layout
#   ... review + verify on /tables ...
cipher emit-tables --dataset-name <name>                   # write verified layouts
cipher resolve-entities --dataset-name <name>
cipher profile-table file.xlsx --summary
cipher profile-table file.csv --mapping edited.json        # re-evaluate around user edits
cipher eval-table-typing                                    # synthetic messy tables
cipher eval-table-typing --labels labels.yaml --combos "header,validators;header,validators,llm"
```

Synthetic results (held-out seed; synthetic tables are easier than real ones, so add real files to
`labels.yaml` before tuning weights):

| detectors | columns | accuracy | macro-F1 | ms/column |
|---|---|---|---|---|
| header | 1,108 | 0.81 | 0.89 | 8 |
| validators | 1,108 | 0.85 | 0.79 | 45 |
| **header + validators** | 1,108 | **0.97** | 0.98 | 46 |
| header + validators (21-table run) | 168 | 0.99 | 0.99 | 48 |
| gliner (CPU, zero-shot) | 168 | 0.42 | 0.37 | 1,562 |
| llm (Qwen3.8-27B, :8008) | 168 | 0.99 | 0.99 | 930 |
| header + validators + gliner | 168 | 0.98 | 0.98 | 1,593 |
| header + validators + llm | 168 | 0.99 | 0.99 | 954 |

Reading:
- **Default:** cheap detectors only. The cascade calls the LLM only when a column stays ambiguous.
- **The LLM is about as accurate alone,** but costs ~20x more per column. It is the only
  detector that reads roles and row relationships on its own, so it earns its place on headerless
  or role-heavy tables (sender/receiver).
- **GLiNER zero-shot classification can't type columns.** With 58 labels it calls almost
  everything `person.full_name`, so leave it out of the default.

On the local Qwen (21-table run): the LLM alone reaches 0.99 at ~930 ms/column. GLiNER zero-shot
reaches 0.42, because it calls most columns person names.

## 12. Gaps found along the way

- **Which groups the text analytics read** is a parameter on each one: `filetype_groups` /
  `--filetype-group` (repeatable). The defaults are in `DEFAULT_FILETYPE_GROUPS`:
  - text extraction: `document` (emails always; images get text from OCR)
  - embedding, selector extraction and NER: `document`, `email`, `image`

  `table` is in none of them, because the column mapping already covers what NER and selectors
  would find. Add it to make spreadsheets keyword/semantic searchable; their text is stored and
  chunked as `document`. The wizard shows "File types" toggles on text extraction and embedding.
  A possible later addition: one sampled summary chunk per table, so a table is findable by
  search without indexing every row.
- **Usernames** are not a field type: a username can be almost anything, so there's no pattern
  worth validating. Passport numbers and plates match only next to cue words (or in a column, whose
  header is the cue); country-specific parsing and attributes come later.
- **pyselectors' `grouped` phone pattern** accepts decimals like `37.2001` (validation then usually
  rejects them). pytabular guards decimals, but the pattern could be tightened.
- **`msisdn`** is a phone cue word in every pyselectors language (plus Russian
  `абонентский номер`). Other header words only pytabular knows could move the same way.
