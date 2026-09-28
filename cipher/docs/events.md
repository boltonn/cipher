# Events & the Calendar

How the event layer fits into CIPHER: dated occurrences — travel, lodging,
reservations, meetings, deadlines, deliveries — pulled from documents (mostly
email) by an LLM, or parsed straight from a calendar (`.ics`) attachment.

Status: **Phase 0 (backend skeleton) landed** — schemas, tables, repository,
Alembic revision `0008_events`, and the `/events` API. Extraction (`.ics`
parser + LLM pass) and the frontend follow in Phases 1–2.

---

## 1. Why

An event is not a graph *identity* like a person, organisation, or place — it is
a dated thing that happened (or will happen). It has temporal extent, a small
set of shared attributes, and links to the people and places involved. It earns
its own layer (like `location`) rather than a new `EntityType`, but it links
back to the entity and location layers where those references resolve.

---

## 2. The shape: a thin row + a typed `details` blob

**`event`** carries only what *every* event has:

```
event(id, dataset_id (NULLABLE) → dataset, file_id → file,
      event_type ∈ travel|lodging|reservation|meeting|deadline|delivery|occasion|other,
      title, summary,
      date_start, date_end, timezone (IANA), is_all_day,
      date_precision ∈ exact|day|month|year|approximate,
      status ∈ confirmed|tentative|cancelled|completed,
      details JSONB,
      -- iCalendar (RFC 5545 VEVENT) fields, carried losslessly from .ics (rev 0016)
      url, categories[], sensitivity ∈ public|private|confidential,
      uid, recurrence_rule (raw RRULE, not expanded), sequence,
      source_created, source_last_modified,
      extractor, extraction_model, confidence, is_verified, tags[], notes,
      date_created, date_updated)
```

### iCalendar coverage

The schema is a **superset of a VEVENT**. `event_type` + `EVENT_CATEGORY`, the
typed `details` union, `date_precision`, `extractor`/`confidence`,
`is_verified`, and the resolved `entity`/`location` links are all things iCal
has no place for. The reverse gap — VEVENT properties CIPHER used to drop on
import — is closed by rev `0016`:

| VEVENT | → |
|---|---|
| `UID` | `event.uid` (identity across updates; primary dedup key) |
| `RRULE` | `event.recurrence_rule` (raw string; **not** expanded — Phase 3) |
| `CATEGORIES` | `event.categories[]` (raw source labels, ≠ analyst `tags[]`) |
| `SEQUENCE` | `event.sequence` (which UID-match supersedes) |
| `URL` | *(parsed but not carried — an event surfaces no clickable link)* |
| `CLASS` | `event.sensitivity` |
| `DTSTAMP` / `CREATED` / `LAST-MODIFIED` | `event.source_created` / `source_last_modified` |
| `GEO` | a geocoded `event_place` (coords → `location`) |
| `DTSTART` / `DTEND` / `DURATION` | `date_start` / `date_end` / `timezone` / `is_all_day` |
| `SUMMARY` / `DESCRIPTION` / `LOCATION` | `title` / `summary` / `event_place.raw_text` |
| `STATUS` | `status` (also carries `completed`) |
| `ORGANIZER` / `ATTENDEE` (`CN`, `mailto:`, `PARTSTAT`, `CUTYPE`) | `event_participant` — see §3 |
| `PRIORITY`, `TRANSP`, `RESOURCES`, `VALARM`, `CONTACT`, `ATTACH`, `RDATE`/`EXDATE`/`RECURRENCE-ID` | **omitted** — reminders / free-busy / recurrence *expansion* are not triage concerns |

Type-specific fields that only make sense for *some* events —
`operator`, `confirmation`, flight `number`, `nights`, `party_size`, `amount` /
`currency` / `payee`, `carrier` / `tracking_number` — live in **`details`**, a
Pydantic **discriminated union** keyed by `kind` (`TravelDetails`,
`LodgingDetails`, `ReservationDetails`, `DeadlineDetails`, `DeliveryDetails`;
`meeting` / `occasion` / `other` carry no detail row). Adding a field to one
event type is an edit to one small model — no migration, no wide nullable
columns on the base table.

`category` (travel / personal / work / admin / logistics) is derived from
`event_type` at read time (`EVENT_CATEGORY`) and drives calendar colour.

Provenance is just **`file_id`** — the source file the row was extracted from.
Dedup keeps one row per real event, so `file_id` points at whichever source
landed first (the booking email or the `.ics`). Span offsets into
`ExtractedText.content` can be added later if the UI wants to highlight the
event in the file text; not needed now.

**`dataset_id` is nullable** (rev `0011`). An event is a dated real-world
occurrence, not an artefact of one ingest — like `location` it can be
analyst-authored or span datasets, and `file_id` already carries provenance.
`dataset_id` stays as an optional scoping *filter* (the `/events` list and
`/events/calendar` both take it or not); it is set when an extraction pass knows
the source ingest, left null otherwise.

Files:
`libs/cipher-schemas/src/cipher/schemas/graph/{event,event_participant,event_place}.py`,
`libs/cipher-datastores/src/cipher/datastores/postgres/tables/{event,event_participant,event_place}.py`,
`libs/cipher-datastores/src/cipher/datastores/postgres/repositories/event.py`.

---

## 3. Links to people and places

Two mirror-image join tables. The FK is nullable — an unresolved name or an
ungeocoded place is still recorded, exactly like an unresolved `mention`.

| table | points at | roles | until resolved |
|---|---|---|---|
| **`event_participant`** | `entity` (person/org) | `traveler` \| `attendee` \| `organizer` \| `host` \| `guest` | `raw_name` + `raw_email` hold the surface text |
| **`event_place`** | `location` | `venue` \| `origin` \| `destination` | `raw_text` holds the surface text |

`event_participant` also carries `raw_email` (the iCalendar `mailto:` address —
the precise key for resolution), `rsvp_status` (iCalendar `PARTSTAT`), and
`is_resource` (iCalendar `CUTYPE` room/resource — skipped by resolution so a
meeting room never becomes a person). The **role vocabulary stays semantic**
(the part someone plays in the real event) rather than adopting iCal's
`ROLE` (CHAIR / REQ- / OPT-PARTICIPANT): that axis overlaps `organizer` /
`attendee` and is empty for the LLM-over-prose path.

Most events get one `venue` row; travel writes `origin` + `destination`.
Participants resolve against the entity layer (so "everything on Jane's
calendar" works, and events surface on the person page); places resolve against
the `location` table (so they plot on the `/locations` map). Both are done by
**`resolve-event-links`** (§5).

---

## 4. API

Router `backend/src/cipher/api/routes/events.py`, prefix `/events`:

| method + path | purpose |
|---|---|
| `GET /events` | list-filter (dataset, file, type, status, date range, `participantEntityId`, `locationId`, `minConfidence`, `isVerified`) → paginated |
| `GET /events/calendar?dateFrom=&dateTo=&datasetId=` | every event whose `date_start` is in the window, ascending (calendar feed) |
| `POST /events` | create (analyst, or an extraction pass) |
| `GET /events/{id}` | one event **with** its participants and places |
| `PATCH /events/{id}` · `DELETE /events/{id}` | update / delete (links cascade) |
| `GET /events/{id}/participants` · `POST /events/{id}/participants` · `DELETE /events/participants/{pid}` | manage participant links |
| `GET /events/{id}/places` · `POST /events/{id}/places` · `DELETE /events/places/{pid}` | manage place links |

---

## 5. Pipeline (Phase 1)

```
load-files → extract-text
          → extract-events            (EVENT_EXTRACTION enrichment, per calendar file — deterministic .ics parse)
          → extract-events --llm      (same enrichment, per email file — pyprompt LLM pass; opt-in; --docs adds documents)
            └ or extract-llm --tasks entities,events   (one pyprompt call per email/doc file → mentions + events
                                        together; completes ENTITY_EXTRACTION + EVENT_EXTRACTION; halves the calls.
                                        --concurrency N in flight; refuses > --max-files (15k) without --yes —
                                        do a --limit slice first. See docs/entities.md §8 "Cost / scale".)
          → resolve-entities          (needed first: it creates the person/org entities and person↔selector edges)
          → resolve-event-links       (participants raw_email/raw_name → entity; places raw_text → location)
```

**`.ics` is deterministic; `--llm` opts in to a model.** `extract-events` parses
a dataset's `.ics` / `text/calendar` files with no model. `extract-events --llm`
additionally runs the **`analytics/pyprompt`** prompt-runner (one process, many
enrichment types) over email bodies (`--docs`: also documents), writing `event`
rows with `extractor = "llm"` deduped against existing rows on `uid`, then
`(normalized title, start date)` / `(type, start date, place)`. It is not part of
the chat agent.

- **`.ics` parsing** — `pyparse.parsers.calendar.ics.IcsParser` (hand-rolled like
  `vcard.py`: line unfold, TEXT unescape, UTC / `TZID=` / all-day `DTSTART`,
  `DURATION`, `STATUS`, `CLASS`, `URL`, `GEO`, `SEQUENCE`, `DTSTAMP` / `CREATED`
  / `LAST-MODIFIED`, `ORGANIZER` / `ATTENDEE` with `CN` / `mailto:` / `PARTSTAT`
  / `CUTYPE`, `RRULE`, `CATEGORIES`). Returns parser-local `ParsedCalendarEvent`
  / `ParsedCalendarPerson`. Unit-tested (`analytics/pyparse/tests/test_ics.py`).
- **`extract-events`** (`pipelines/cipher-orchestration/.../extract_events.py`,
  CLI `cipher extract-events`) — queues an `EVENT_EXTRACTION` enrichment for each
  `text/calendar` file, then one `event` row per `VEVENT` (`extractor = "ics"`,
  `file_id` set) carrying the full iCal field set (§2). `event_type` is inferred
  from CATEGORIES + SUMMARY keywords. ORGANIZER / ATTENDEE become unresolved
  `event_participant` (`raw_name` + `raw_email` + `rsvp_status` + `is_resource`)
  rows; `LOCATION` an `event_place` (`raw_text`), or — when `GEO` is present — a
  geocoded `location` linked by `location_id`.
- **`extract-events --llm`** (`extract_text_events_workflow`) — queues an
  `EVENT_EXTRACTION` enrichment for each **email** (with `--docs`, also
  **document**) file, runs `analytics/pyprompt`'s `events` pack over its
  extracted text **anchored to the file's authored date** (`EmailMetadata.date_sent`
  / `DocumentMetadata.date_content_created`) so relative dates resolve, and
  writes one `event` row per returned event (`extractor = "llm"`,
  `extraction_model` / `confidence` / typed `details` set). Skips an
  event already in the dataset by the dedup keys above. Needs `pyprompt` and an
  `LLM__*` config; `--llm-only` skips the `.ics` pass.
- **`resolve-event-links`** (`resolve_event_links.py`, CLI
  `cipher resolve-event-links`) — dataset-wide, re-runnable. Matches an
  `event_participant` by `raw_email` → the owning `selector`'s person/org, then
  by `normalize_name(raw_name)` against an existing `person` then `organization`
  (`PostgresEntityRepository.find_by_normalized_name`); matches an `event_place`
  by `normalize_name(raw_text)` against an existing `location.name`. Rooms /
  resources are skipped and **nothing is created** — an unmatched link stays as
  `raw_name` / `raw_text` (mirrors `resolve-entities`' untyped-name rule). Run
  after `resolve-entities`. No geocoder in-repo, so most `event_place` rows from
  free text stay unresolved for now.
- **`reset-events`** (`reset_events.py`, CLI `cipher reset-events`) — drops a
  dataset's extraction-built `event` rows (participant/place cascade, both `ics`
  and `llm`), keeping `extractor = manual` and analyst-verified rows, and clears
  the `EVENT_EXTRACTION` enrichments. Mirrors `reset-entities` / `reset-text`.

Not yet wired: `.ics` files only become their own `File` rows once email
attachment extraction persists them (`extract-text`) — verify that path feeds
`text/calendar` files in before expecting output.

---

## 6. Frontend (Phase 2 — landed)

`cipher-frontend/features/events/` + `app/(app)/events/page.tsx`, nav item under
**Viewers**. No dataset gate — the page opens on all events; the `DatasetSelect`
in the header is an optional filter.

- **filter bar** (`event-filters.tsx`) — type / status / verified / date range,
  rendered **above the tabs** so it drives both views. The table passes the
  filters to `/events`; the calendar narrows type/status/verified/title
  client-side (`lib/filter.ts`) since `/events/calendar` only takes a window, and
  the date-range control is hidden there (month nav is its date control).
- **calendar** (`events-calendar.tsx`) — month grid, chips coloured by `category`
  (`event-type-meta.tsx`, a documented local palette; amber stays reserved for
  the AI-extracted affordance), cancelled events struck through, `+N more`
  overflow. Week / agenda views are a follow-up.
- **table** (`events-table.tsx`) — plain sortable table (the `entities-table`
  pattern) + server `Pagination`.
- **detail sheet** (`event-detail-sheet.tsx`) — when/where, participants linking
  to `/entities/{id}` (with `rsvp_status` / resource markers), places to the map,
  the typed `details` block, `categories` chips, a recurrence badge, and a
  provenance footer (source `fileId`, extractor / model / confidence,
  `sensitivity`, `uid`), `Mark verified`.
- **person page** — `PersonEventsSection` (`participantEntityId` filter) renders
  on the dossier once `resolve-event-links` links an event to the person.
- **map** — plotting `event_place` on the maplibre viewer / travel arcs is still
  to do.

---

## 7. Migrations

`0008_events` — the three event-layer tables and their indexes. Purely
additive; no existing table is altered. Follows the `0002_entities` pattern
(`Base.metadata.create_all(..., tables=event_layer_tables(), checkfirst=True)`),
so it is a safe no-op on a `create_all` database.

`0011_event_dataset_nullable` — `ALTER TABLE event ALTER COLUMN dataset_id DROP
NOT NULL`. For a dev `create_all` DB, apply `scratchpad/apply_0011.sql`.

`0016_event_ical_fields` — additive `ALTER TABLE`: `event` gains `url`,
`categories`, `sensitivity`, `uid` (indexed), `recurrence_rule`, `sequence`,
`source_created`, `source_last_modified`; `event_participant` gains `raw_email`
(indexed), `rsvp_status`, `is_resource`. Every column is nullable / defaulted, so
it is a safe no-op on a `create_all` DB. For a dev DB, apply
`scratchpad/apply_0016.sql`.

---

## Phasing

| phase | scope | status |
|---|---|---|
| **0** | `event` / `event_participant` / `event_place` schemas + tables + repository, `/events` API, `EVENT_EXTRACTION` enrichment type, Alembic `0008` | **landed** |
| **1** | `pyparse` `.ics` parser (unit-tested), deterministic `extract-events` (`.ics` → events), `reset-events`, `stats` | **landed** — remaining: confirm `.ics` files land as `File` rows |
| **1b** | LLM free-text event extraction — `analytics/pyprompt` prompt-runner (`events` pack) wired into `extract-events --llm` | **landed** — opt-in; needs an `LLM__*` config. Anchored to authored date, typed `details` / `url` / `confidence`, `--docs` widens past email |
| **1c** | iCal superset (rev `0016`): `uid` / `recurrence_rule` / `categories` / `sequence` / `url` / `sensitivity` / source timestamps on `event`; `raw_email` / `rsvp_status` / `is_resource` on `event_participant`; `GEO` → geocoded place. `resolve-event-links` sweep (participant/place → entity/location) | **landed** — `event_place` from free text needs a geocoder |
| **2** | `features/events/` month calendar + table + filter bar + detail sheet, person-page section, nav item | **landed** — remaining: week/agenda calendar views, `event_place` on the map / travel arcs |
| **3** | trips (`event_group`), `supersedes_event_id` reschedule chains, recurrence **expansion** (RDATE/EXDATE/RECURRENCE-ID → instances), `.ics` subscription export, agent `find_events` tool | |
