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
event(id, dataset_id, file_id → file,
      event_type ∈ travel|lodging|reservation|meeting|deadline|delivery|occasion|other,
      title, summary,
      date_start, date_end, timezone (IANA), is_all_day,
      date_precision ∈ exact|day|month|year|approximate,
      status ∈ confirmed|tentative|cancelled|completed,
      details JSONB,
      extractor, extraction_model, confidence, is_verified, tags[], notes,
      date_created, date_updated)
```

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
| **`event_participant`** | `entity` (person/org) | `traveler` \| `attendee` \| `organizer` \| `host` \| `guest` | `raw_name` holds the surface text |
| **`event_place`** | `location` | `venue` \| `origin` \| `destination` | `raw_text` holds the surface text |

Most events get one `venue` row; travel writes `origin` + `destination`.
Participants resolve against the entity layer (so "everything on Jane's
calendar" works, and events surface on the person page); places resolve against
the `location` table (so they plot on the `/locations` map).

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
          → extract-events   (EVENT_EXTRACTION enrichment, per calendar file — deterministic .ics parse)
          → [resolve links]  (participants raw_name → entity; places raw_text → location; reuses the entity/location paths)
```

**Deterministic only.** `extract-events` parses a dataset's `.ics` /
`text/calendar` files; it does **not** call a model. LLM extraction over
free-text email bodies is a **separate future prompt-runner service** (one
process serving many enrichment types), not part of this pipeline or the chat
agent.

- **`.ics` parsing** — `pyparse.parsers.calendar.ics.IcsParser` (new `calendar/`
  category, hand-rolled like `vcard.py`: line unfold, TEXT unescape, UTC /
  `TZID=` / all-day `DTSTART`, `DURATION`, `STATUS`, `ORGANIZER` / `ATTENDEE`,
  `RRULE`, `CATEGORIES`). Returns parser-local `ParsedCalendarEvent`s. Unit-tested
  (`analytics/pyparse/tests/test_ics.py`).
- **`extract-events`** (`pipelines/cipher-orchestration/.../extract_events.py`,
  CLI `cipher extract-events`) — queues an `EVENT_EXTRACTION` enrichment for each
  `text/calendar` file, then one `event` row per `VEVENT` (`extractor = "ics"`,
  `file_id` set). `event_type` is inferred from CATEGORIES + SUMMARY keywords.
  ORGANIZER / ATTENDEE become unresolved `event_participant` (`raw_name`) rows,
  LOCATION an unresolved `event_place` (`raw_text`) row.
- **`reset-events`** (`reset_events.py`, CLI `cipher reset-events`) — drops a
  dataset's extraction-built `event` rows (participant/place cascade), keeping
  `extractor = manual` and analyst-verified rows, and clears the
  `EVENT_EXTRACTION` enrichments. Mirrors `reset-entities` / `reset-text`.

Not yet wired: `.ics` files only become their own `File` rows once email
attachment extraction persists them (`extract-text`) — verify that path feeds
`text/calendar` files in before expecting output. Participant/place →
entity/location resolution is the `[resolve links]` sweep, still to build.

---

## 6. Frontend (Phase 2)

`cipher-frontend/features/events/` — same layout as `features/locations/`:

- **calendar** (month / week / agenda), coloured by `category` via design
  tokens; amber reserved for the "AI-extracted / unverified" affordance;
  cancelled events struck through; fuzzy-date events float on a day/week band
- **table** — TanStack Virtual, filter by type/status/date/participant/place,
  paginated + infinite scroll
- **detail sheet** — when/where, participants linking to person pages, the typed
  `details` block, source file link
- **map** — plot `event_place` locations on the existing maplibre viewer;
  travel as arcs origin→destination
- **person page** — an "Events" section next to the entity dossier

---

## 7. Migrations

`0008_events` — the three event-layer tables and their indexes. Purely
additive; no existing table is altered. Follows the `0002_entities` pattern
(`Base.metadata.create_all(..., tables=event_layer_tables(), checkfirst=True)`),
so it is a safe no-op on a `create_all` database.

---

## Phasing

| phase | scope | status |
|---|---|---|
| **0** | `event` / `event_participant` / `event_place` schemas + tables + repository, `/events` API, `EVENT_EXTRACTION` enrichment type, Alembic `0008` | **landed** |
| **1** | `pyparse` `.ics` parser (unit-tested), deterministic `extract-events` (`.ics` → events), `reset-events`, `stats` | **landed** — remaining: confirm `.ics` files land as `File` rows, participant/place resolution sweep |
| **1b** | LLM free-text event extraction — a **separate prompt-runner service** for many enrichment types (not the chat agent) | future, user-enabled |
| **2** | `features/events/` calendar + table + detail + map, person-page section | next |
| **3** | trips (`event_group`), `supersedes_event_id` reschedule chains, recurrence rules, `.ics` subscription export, agent `find_events` tool | |
