# My workspace — ideas backlog

`/me` is the user's own corner of the app. Today it shows saved searches, recent
searches, the datasets you can open, tag metrics, and a link to Settings. This file
collects knowledge-management features that **don't exist yet**, so they can be
picked up one at a time. Nothing here is designed in detail.

Notes on cost: "new table" marks ideas that need one (the house preference is a
flag or column on an existing table where possible — see `docs/glossary.md`).

## Searches

- **Alerts on saved searches** — re-run each saved search after an ingest or
  enrichment pass and show "12 new results since you last looked". Needs a
  `date_last_seen` on `search` plus a post-pipeline hook; the result count is
  already in `ResultShape`.
- **Share a saved search** with the other members of its datasets (read-only).
  A `is_shared` flag on `search`; access is the dataset membership already there.
- **Rename / group saved searches** — inline rename on `/me` (the API already
  takes `name`); grouping would need a `folder` column.
- **Search diff** — compare two runs of the same saved search: what appeared,
  what dropped out.

## Collections (casework)

- **Collections** — named sets of files, passages, images and entities you pin
  while working ("Travel 2019", "Payments to X"), each with a short note and an
  export (CSV / zip of files with citations). New table: `collection` +
  `collection_item`.
- **Pin from chat** — add a chat answer and its citations to a collection.
- **Watchlist** — follow an entity; `/me` lists new mentions, merges or
  relationships since you last checked.

## Review

Review stays built into each page; `/me` would only summarise it.

- **Your open review work** — counts of pending items in the datasets you can
  access (Resolve groups, face matches, mention corrections, tags awaiting a
  decision), each linking to the filtered page.
- **Your recent decisions** — accepts, rejects, merges and tag labels you made
  this week, with undo where the action supports it.
- **Disagreements** — targets where two analysts, or an analyst and a model,
  labelled the same tag differently.

## Tags

- **Tag glossary** — a description per tag, which models produce it, and
  rename / merge (rewrites `tag` rows and rebuilds the read copies).
- **Training readiness** — *built, admin-only*: `/admin/tag-training` shows analyst
  positives / negatives per image tag against the head minimum. Still open: a
  "train heads" action from that page, and the last trained head's metrics
  (AP / F1 / threshold) beside each tag.
- **Model agreement** — for tags with both analyst labels and model scores,
  precision at the current threshold and a suggested threshold.
- **Drift** — model positive rate per tag per ingest, to spot a model going off.

## Datasets

- **Dataset health** — enrichment completeness, profiles recomputed since the AI
  summary was written ("summary outdated"), stale embeddings.
- **Access requests** — status of requests you made for locked datasets; for
  admins, requests waiting on them.
- **Dataset changelog** — what was loaded or re-run, by whom, when (from
  `enrichment_run`).

## Knowledge

- **Resolution coverage** — share of mentions resolved per dataset and the
  largest unresolved name groups (the "nick bolton" case), linking to Resolve.
- **Weekly digest** — an AI-written summary of what changed in your datasets
  (new people, busy threads, new events), built from the dataset profile like
  the dataset summary.
- **Ontology browser** — the entity / relationship types and how many of each
  exist.

## Chat

- **Chat history** — past conversations, searchable, reopenable; today they live
  only in the browser.

## Personal settings

- Defaults: dataset, search mode (text / semantic / hybrid), exact match,
  pagination vs infinite scroll.
- Personal API tokens for scripts against the backend.
