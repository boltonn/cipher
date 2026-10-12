# `cipher` CLI reference

Every `cipher` command, what it's for, and when you'd reach for it. The **order** to run
the pipeline in is in `docs/running-analytics.md` (the runbook); why each enrichment
exists is in `docs/enrichments.md`; vocabulary is in `docs/glossary.md`.

Almost every command takes `--dataset-name` or `--dataset-id`; that's left out of
the tables below. `cipher <command> --help` lists every option. Commands are re-runnable:
work is tracked per file in the `enrichment` table (or deduped on a natural key), so a
re-run picks up what's still pending.

**Keeping this set small.** A command earns a place here only if you'd run it again:
a pipeline step, or a tool for maintaining data after the code changes. A one-time repair
belongs in a migration or a scratch script that gets deleted afterwards, not here.
When you add or remove a command, update this page.

---

## Pipeline steps

What turns a directory of files into an enriched dataset, roughly in runbook order.

### Stage

| Command | What it does | Notable options |
|---|---|---|
| `create-tables` | Create every Postgres table (idempotent). On an empty database, stamp it at the latest migration. | `--stamp-head` |
| `create-dataset` | Create an empty dataset. | `--description` |
| `load-files <uri>` | Stage a directory or `s3://bucket/prefix/` into a dataset: crawl it, type and hash each file, write `file` rows pointing where the files already are (nothing copied). Skips files already staged, so it resumes. No analysis. | `--include`, `--exclude` (globs on the path below the uri), `--limit` |
| `extract-archives` | Unpack zip / tar (also `.tar.gz` `.xz` `.bz2` `.zst`), and 7z / rar / iso / cab when `7zz` is installed (sandboxed), into member files; encrypted members are tried with each password in the passwords file, and archives are retried when it changes (`parent_id` = the archive, bytes in the output store) and decode compressed files (`report.csv.gz`) into their rows. Nested archives pass by pass; duplicates, too-deep and self-containing archives skipped; resumes. `extract-text` runs it first. | `--max-depth`, `--max-total-gib`, `--max-ratio`, `--min-free-gib`, `--output-uri`, `--max-archive-gib`, `--sandbox best_effort|required|off`, `--passwords-file` |

### Text

| Command | What it does | Notable options |
|---|---|---|
| `extract-text` | Unpacks archives, then text and structure from each eligible file (emails and unpacking loop until nothing new turns up, then documents); records image-based pages for `ocr`. | `--filetype-group`, `--no-archives`, `--no-inline-images` (don't save images email bodies show), `--ocr-backend easyocr` (no GPU), `--chunker`, `--chunk-size` |
| `ocr` | Read image-based PDF pages and text-bearing images with pyvllm's `ocr` model (it starts and stops the model). Images pass a CLIP "has text" gate first. | `--all-images`, `--clip-threshold`, `--force`, `--concurrency` |
| `embed-text` | Chunk and embed extracted text into the search store. Finishes by anchoring mentions to their chunks (`mention.chunk_id`). | `--chunk-size`, `--chunk-overlap`, `--max-pages`, `--skip-email-state`, `--device` |
| `summarize` | Short AI summary per file. Opt-in: one LLM call per file. | `--filetype-group`, `--limit`, `--language` |

### Images and faces

| Command | What it does | Notable options |
|---|---|---|
| `embed-images` | CLIP image embeddings (and, with `--classify`, tag scores). | `--classify`, `--min-image-side`, `--device` |
| `train-image-heads` | Train one small classifier per image tag from analyst labels. Re-run as labels grow. | `--tag`, `--min-positives` |
| `score-image-heads` | Score embedded images with the trained tag heads. | `--tag`, `--min-score` |
| `extract-locations` | EXIF GPS → map points. No model. | |
| `detect-faces` | Face detection, embedding and quality score. | `--min-image-side`, `--device` |
| `match-faces` | Propose face → person matches from each person's best faces. | `--similarity`, `--verified-only`, `--reset` |
| `reject-similar-faces` | Auto-reject faces that look like ones an analyst marked "not a face". Re-run after review. | `--similarity` |
| `cluster-faces` | Group unassigned faces into unnamed persons. | `--similarity`, `--min-faces`, `--reset`, `--reset-verified` |
| `link-face-cooccurrence` | Rebuild `appears_in_photo_with` edges from current face state (prunes stale ones). Run after face review. | `--min-verified-photos` |

### Mentions

| Command | What it does | Notable options |
|---|---|---|
| `extract-selectors` | Phones, emails, websites, IBANs, … from text, as selector mentions. Links each website to the organization named like it. Phones get a country only when the number states one. | `--filetype-group`, `--rescan` |
| `extract-entities` | Person / organization / location names (NER) and relations; skips quoted copies of emails already in the dataset. | `--extractor nerd\|gliner\|llm`, `--threshold`, `--rescan` (keeps resolutions) |
| `extract-llm` | Entities, relations and events in one LLM call per email (fewer calls than `extract-entities --extractor llm` + `extract-events --llm`). | `--tasks`, `--docs`, `--limit`, `--yes` |
| `extract-events` | Events from `.ics` files; `--llm` adds email bodies behind a GLiNER gate. | `--llm`, `--llm-only`, `--gate-threshold` |
| `extract-contact-entities` | vCards → contacts → resolver-ready mentions. | |
| `extract-signatures` | Each sender's **email signature**: person, organization → unit chain, role, address (with its city from the gazetteer), phones / emails / website, plus the relationships between them. Reviewed on the Entities page's *Email signatures* tab. | `--rebuild`, `--include-bulk`, `--limit`, `--concurrency` |
| `extract-relationships` | Directed `emailed` edges between email address selectors. | `--rebuild` |

### Tables

| Command | What it does | Notable options |
|---|---|---|
| `map-tables` | Profile tabular files and propose a column → ontology mapping per header layout (reviewed on `/tables`). | `--reprofile`, `--repropose`, `--region` |
| `emit-tables` | Write mentions, map points and edges for tables whose mapping is verified; then `resolve-entities`. | |

### Resolve

| Command | What it does | Notable options |
|---|---|---|
| `resolve-entities` | The whole resolution stage: same names, match names, match new entities, places (gazetteer), links and suggestions. Incremental unless `--full`. | `--full`, `--concurrency`, `--skip-locations`, `--auto-threshold`, `--review-low` |
| `resolve-locations` | Just the places step: location mentions → global place entities. Re-run alone after adding a custom place (`custom_places.jsonl`). | |
| `resolve-event-links` | Just the event step: participant and place links → entities / locations. Re-run after `extract-events`. | |
| `profile-dataset` | Recompute the dataset profile behind the empty-query search briefing. | `--all` |

---

## Maintenance

For keeping stored data right as the code changes, undoing a step, or seeing where a
dataset stands.

### After changing normalization code: `rekey`

Names, the resolver's name-key index and selector values are stored already normalized.
After changing the code that normalizes them, `rekey` brings existing rows in line with
what a fresh extraction would write, so old and new spellings of one thing still meet.
It runs the first three parts unless you narrow it (`--filetypes` only when asked), and is idempotent.

| Part | Run after changing | What it does |
|---|---|---|
| `--names` | `normalize_name` (`cipher.datastores.postgres.utils`) | Re-keys name mentions, entity display keys and name-group resolutions; trims quotes and possessives off name spans. **Follow with `resolve-entities`** so duplicates the old keys made get folded. |
| `--name-keys` | cipher-names (`entity_keys`) | Rebuilds the `entity_name_key` index. Add `--purge-name-keys` (all datasets only) after a `KEYS_VERSION` bump. Entity writes keep it current otherwise. |
| `--selectors` | pyselectors (packs, normalizers, validators) | Refreshes each selector's attributes (merged over the stored ones); a value that now normalizes differently is re-keyed with its mentions, folding into the selector that already has the new value. Values that no longer validate are reported, never deleted. |
| `--filetypes` (opt-in, reads every file) | filetyper (registry, heuristics, compression look-inside) | Re-types files: type fields, `is_encrypted`, plus `compression` for a file found compressed (`report.csv.gz` → csv, `logs.tar.gz` → tar). Hashes untouched. Not part of the default run. |

Always look first: `cipher rekey --dataset-name rag --dry-run` counts what would change
and writes nothing.

### Undo and retry

| Command | What it does |
|---|---|
| `retry-failed <analytic>` | Put one analytic's failed rows back to pending (`cipher retry-failed signature_extraction --dataset-name rag`); re-run that step to process them. |
| `reset-text` | Delete indexed text chunks and set extraction/embedding back to pending (changed chunk size or embedding model). |
| `reset-entities` | Delete the extraction-built entity layer (manual entities are kept); then re-run the mention steps. |
| `reset-events` | Delete extraction-built events (manual / verified kept). |
| `extract-signatures --rebuild`, `extract-relationships --rebuild`, `match-faces --reset`, `cluster-faces --reset` | Per-step redo, on the step itself. |

### Status and housekeeping

| Command | What it does |
|---|---|
| `stats` | File inventory and enrichment status for a dataset. |
| `estimate` | Remaining wall time per enrichment, from measured rates on this machine. |
| `rates` | Measured throughput (median seconds per unit) and recent runs. |
| `prune-search-history` | Delete unsaved search records not run recently (saved searches kept). `--days` |

### Running plans

| Command | What it does | Key options |
|---|---|---|
| `worker` | Run approved plan steps from the database on this host (`docs/pipeline-runner.md`): claims the next step its pool can run, runs the `cipher` command, heartbeats, stops a step when it's cancelled. One per host and pool; Ctrl-C drains, twice interrupts. | `--pool cpu\|gpu`, `--slots`, `--gpu` (repeatable), `--llm-cap`, `--max-hosts-per-step`, `--strict-version`, `--log-dir` |
| `runs` | What is queued or running right now, across hosts: each step's host, worker pid, step pid, log file and last heartbeat, or what a queued step waits for. On a host: `tail -f <log>`, `ps -g <pid>`. | `--here` (this host only) |

---

## Measurement and evaluation

For deciding whether a change made things better. No dataset writes except where noted.

| Command | What it does |
|---|---|
| `benchmark-ingest` | Real ingest throughput (file typing, email / document extraction) over a local directory. |
| `benchmark-storage` | Postgres upsert / read latency and on-disk size for extracted text (writes, then deletes, unless `--keep`). |
| `profile-table` | Type one table's columns onto the ontology and print the proposed mapping. |
| `eval-table-typing` | Compare column-typing detectors on labelled or synthetic messy tables. |

Evaluation scripts outside the CLI live in `scripts/`. `eval_signatures.py` scores
`extract-signatures` on a synthetic multilingual set; `eval_email_text.py` audits email
text extraction; `bench_global_search.py` and `make_scale_bench.py` time global search;
`make_signature_demo_emails.py` and `seed_org_chart_demo.py` build synthetic demo
datasets.

---

## Retired

Removed on 2026-10-07 because each did a one-time job (or a job the pipeline now does on
its own). Don't bring them back as commands; write a migration or a throwaway script.

| Was | Now |
|---|---|
| `refold-names`, `backfill-entity-name-keys`, `refresh-selectors` | `rekey --names`, `--name-keys`, `--selectors` |
| `backfill-mention-chunks` | the end of `embed-text` |
| `score-faces` | `detect-faces` scores quality as it detects |
| `backfill-exif-locations` | `extract-locations` |
| `reclassify-domains` | `extract-entities` drops website spans; `extract-selectors` links websites to organizations |
| `sync-chunk-entities` | Elasticsearch entity filters resolve live from `mention.chunk_id` |
| `scripts/backfill_person_entities.py` | person entities are created with the person |
