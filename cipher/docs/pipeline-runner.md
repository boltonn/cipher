# Pipeline runner

**Status:** built 2026-10-12 (§14 lists what was built and where it differs from the design).

**One-line version:** Postgres is the queue. An admin approves a run plan for a dataset; a
`cipher worker --pool cpu|gpu` daemon on each host claims the next step it can run, runs the
existing `cipher` command as a subprocess, and heartbeats. Files come from S3. The per-file
`enrichment` queue already splits work safely between hosts, so the new part is only the step
layer above it.

---

## 1. What exists today

| Piece | Where | What it gives the runner |
|---|---|---|
| Per-file queue | `enrichment` rows, claimed with `FOR UPDATE SKIP LOCKED` (`PostgresEnrichmentRepository.get_pending_batch`) | Several hosts running the same step already split files without overlap. Pausing is just stopping: the undone files stay `pending`. |
| Run record | `enrichment_run` + `record_run()` (`run_recorder.py`) | One row per command invocation: status, params, unit count, duration, `progress` JSONB. The UI's progress views and `cipher estimate` read it. |
| Step order | `ENRICHMENT_DEPENDENCIES`, `resolve_enrichment_order()` | The order of a plan, prerequisites included. |
| Step params | `ANALYTIC_PARAM_MODELS`, `ANALYTIC_COMMANDS` (`dataset_request.py`), mirrored to CLI options by `test_request_params.py` | A plan step is `(enrichment_type, params)` and turns into one `cipher <command> --opts` line. |
| Request wizard | `/datasets/[id]` request flow → `POST /dataset-requests` | Today it files a **GitHub issue** holding the commands; a person runs them by hand. |
| Per-step environments | `ensure_stage_env()` | A host installs only the uv extras the step needs, from `uv.lock`, the first time it runs it. |
| Model servers | `cipher ocr` starts/stops pyvllm's `ocr` model; `llm` runs on :8008 | LLM and OCR are already HTTP services, not in-process models. |
| File reads | `cipher.utils.io.local_path(uri)` | The one place a `uri` becomes bytes. `s3://` raises `NotImplementedError` today. |
| Blob store | `LocalBlobStore`, `BLOB_ROOT`, key `<sha256[:2]>/<sha256[2:4]>/<sha256>` | Archive members already live by content hash, so moving them to S3 is a key prefix change. |

**A gotcha found while reading:** `record_run` calls `close_interrupted_runs`, which marks
**every** `running` row for the same step + dataset `stopped`, and `reset_stuck_enrichments`
returns any claim older than 60 minutes to `pending`. Both assume one process per step per
dataset. With two CPU hosts on one step, the second would close the first one's run row. The
runner has to fix this (heartbeats, §5) before two hosts share a step.

## 2. Shape

```
             web + API host                         Postgres primary (via pgbouncer)
  ┌──────────────────────────────┐            ┌──────────────────────────────────┐
  │ wizard → plan → estimate      │  insert    │ enrichment_run rows (one per step)│
  │ admin approves / pauses       │──────────▶ │ enrichment rows (one per file)    │
  │ progress views (unchanged)    │◀────────── │                                   │
  └──────────────────────────────┘   read     └──────────────────────────────────┘
                                                   ▲ claim / heartbeat ▲
                          ┌────────────────────────┘                    └──────────────┐
             CPU host(s): cipher worker --pool cpu                 GPU host: cipher worker --pool gpu
             runs `cipher <step>` subprocesses                     runs in-process model steps,
             LLM/OCR steps call pyvllm over HTTP ─────────────────▶ hosts pyvllm `llm` + `ocr`
                          │                                                 │
                          └────────────── S3 (files + blobs) ◀──────────────┘
```

- The API never SSHes anywhere. Workers need outbound access to Postgres, S3 and (CPU hosts)
  the GPU host's pyvllm ports. Nothing connects in to a worker.
- More admin CPU servers simply mean more workers on the `cpu` pool.

## 3. Steps, pools and services

A **pool** is the kind of host a step must run on. There are two: `cpu` and `gpu`. LLM work
is not a third pool. The LLM is always a **service**: an OpenAI-compatible endpoint on its
own GPU machine (ours or someone else's). An LLM step is a CPU process making HTTP calls, so
it runs on a CPU host and lists the service it needs; the LLM code paths (`pyprompt`) don't
change. A cap per service (default 1 step at a time) stops two steps from flooding it.

| Step | Pool | Needs service | Scope |
|---|---|---|---|
| `extract-archives`, `extract-text`, `extract-locations`, `extract-selectors`, `extract-contact-entities`, `extract-relationships` | cpu | | per file |
| `ocr` (starts pyvllm's `ocr` model on the GPU the worker gives it) | gpu | | per file |
| `embed-text`, `embed-images`, `detect-faces` | gpu | | per file |
| `extract-entities --extractor nerd\|gliner` | gpu | | per file |
| `extract-entities --extractor llm`, `extract-signatures`, `summarize`, `extract-llm` | cpu | `llm` | per file |
| `extract-events` (`.ics` only) | cpu | | per file |
| `extract-events --llm` (GLiNER gate, then LLM) | gpu | `llm` | per file |
| `map-tables` (`llm` detector adds the service) | cpu | (`llm`) | per file |
| `match-faces`, `cluster-faces`, `resolve-entities`, `profile-dataset` | cpu | | **whole dataset**: one at a time per dataset |

The pool and services come from the step's params (the `--extractor` choice changes the
pool), so they belong next to `ANALYTIC_PARAM_MODELS` as one function, not a hand-kept table.

## 4. The queue: hand-rolled vs Procrastinate

The volume is tiny: a plan is ~5–20 steps, a busy week is a few hundred step claims. The
millions of file claims stay in the `enrichment` table either way. So the question is not
throughput but how much of the runner's actual logic a library would carry.

| | Hand-rolled on `enrichment_run` | Procrastinate |
|---|---|---|
| Tables | A few columns on `enrichment_run` (§5). No new table. | Its own schema (jobs, events, workers, periodic) with **its own migration files**, outside Alembic. Steps would live in two places: its job row and our `enrichment_run` row. |
| Driver | asyncpg / SQLAlchemy, as now | psycopg 3 connector (a second Postgres driver next to asyncpg + psycopg2). |
| pgbouncer (transaction mode) | Polling every few seconds; nothing session-scoped. | LISTEN/NOTIFY doesn't pass through transaction pooling: turn it off and poll, or give workers a direct primary connection. |
| Pools | `WHERE pool = $1` | Queues: fits. |
| Dependencies between steps | `depends_on` checked in the claim query | None built in. Each task enqueues the next on success, or a parent task waits. |
| Per-service caps (`llm` ≤ N runs) | A count in the claim query | `lock` only gives a cap of 1. A cap of N is custom either way. |
| One GPU per in-process step | Same count, by device | Custom either way. |
| Retries, cancel, lost workers | We write them: heartbeat column, `cancelling` status, reclaim on a stale heartbeat. | Built in: retry strategies, abort requests, worker heartbeats and stalled-job lookup (v3). |
| Admin view | Our UI already reads `enrichment_run` | Its CLI/shell, or our UI reading its tables. |
| Code size (estimate) | ~300 lines: claim query, worker loop, heartbeat, cancel | Less queue code, but the dependency, cap and GPU logic above is still ours, plus glue to keep two row types in step. |

**Recommendation: hand-rolled.** Procrastinate is good at many small jobs fanned out to
Python functions. This runner has few, long jobs that run a subprocess, and the hard parts
(dependencies, service caps, GPU holds, the fix to `record_run`) aren't in any queue library.
It also keeps to one table and one migration history. If later we want periodic jobs (nightly
`profile-dataset`, prune search history) and the hand-rolled loop is growing features,
revisit; the steps stay plain `cipher` commands, so switching costs little.

## 5. Worker lifecycle

**Plan rows.** Approving a plan writes one `enrichment_run` row per step with
`status='queued'`. New columns (one migration):

| Column | Purpose |
|---|---|
| `plan_id` | Groups the steps of one approved plan |
| `depends_on` | `enrichment_run` ids that must be `completed` first |
| `pool` | `cpu` / `gpu` |
| `services` | e.g. `{llm}` |
| `worker` | host name + pid of the claimer |
| `date_heartbeat` | updated every ~30 s while running |
| `requested_by` | the approving user (from the session) |

Status gains `queued`, `cancelling`, `cancelled` next to `running` / `completed` / `failed` /
`stopped`. A step is a queued row; a hand-run `cipher` command keeps writing a row as now.

**Claim.** In one short transaction: take a transaction-scoped advisory lock (serialises
claims so cap counts can't race; claims are rare), pick the oldest `queued` row for this pool
whose dependencies are done, whose services are under their caps, and that isn't a
whole-dataset step already running on the same dataset; set it `running` with
`worker` + `date_heartbeat`. Transaction-scoped advisory locks work through pgbouncer.

**Run.** `cipher <command> --dataset-name … --opts` as a subprocess, with
`CIPHER_RUN_ID=<row id>` so `record_run` adopts the queued row instead of opening a new one.
`ensure_stage_env` syncs the extras the first time. Logs go to a file per run on the host,
with the last lines copied into `error_message` on failure.

**Heartbeat, lost workers, the gotcha in §1.** The worker updates `date_heartbeat`. A
`running` row with a heartbeat older than ~2 min is lost: the next claim marks it `stopped`
and re-queues it. `close_interrupted_runs` and `reset_stuck_enrichments` switch from "every
running row" / "older than 60 min" to "rows whose run's heartbeat is stale". Per-file claims
need to know their run for that: either an `enrichment.run_id` column, or keep the time rule
but only when no live run of the step exists. Decided: `run_id`.

**Several hosts on one per-file step.** Allowed: each worker that claims "the step" gets its
own run row (a copy with the same `plan_id`), the file queue splits the work, and the step
counts as done when its files are. Whole-dataset steps never split.

**Cancel / pause.** The UI sets `cancelling`; the worker sees it on its next heartbeat and
sends SIGTERM. Commands commit per batch, so stopping loses at most one batch. `record_run`
needs to catch SIGTERM and close the row `stopped` (today only `Exception` is caught).
"Resume" re-queues the step; its undone files are still `pending`.

**Version check.** Every run row records the branch, git SHA and `uv.lock` hash it actually
ran on, and the plan records the ones it was approved under. A worker on different code
still runs the step (running a branch on purpose is normal), and the step shows a warning:
"ran on `feature-x` @ `abc123`, approved on `main` @ `def456`". A worker setting can make it
refuse instead. The recorded SHA also lets the same step on two branches be compared later.

## 6. GPU hosts

- **The LLM has its own GPU machine** and is always reached over HTTP (§3). Our GPU host is
  for in-process models: embeddings, faces, NER, GLiNER, and OCR.
- The worker treats each GPU as a slot: a step holds one while it runs. `--pool gpu` claims a
  step only when a slot is free. Two in-process steps on one GPU is possible (they're small)
  but not by default.
- `ocr` is still a pyvllm model on our GPU host, so the `ocr` step is a `gpu` step: `cipher ocr`
  starts the model on the GPU the worker gives it (`CIPHER_GPU`) and stops it when done, so
  the GPU is free for other steps the rest of the time.
- CPU workers reach services by URL (`LOCAL_LLM_BASE_URL`, the OCR URL). A step that finds its
  service down returns its claims (`RunStoppedError`) and the run shows `stopped` with the
  reason, as today.

## 7. Files: local or S3, same code

**Nothing new on the dataset.** Where files come from and where Cipher writes are parameters
of the steps that use them, recorded in `enrichment_run.params` like every other step option:

- **Reading:** `load-files <uri> --include … --exclude …`. The uri is a directory or
  `s3://bucket/prefix/`. We never write there. Each `file.uri` then says exactly where its
  file lives (`s3://their-bucket/their/prefix/a.pdf`), so later steps never need to know
  where the dataset came from.
- **Writing:** files Cipher creates itself (archive members, decoded `.gz` files, later email
  attachments) go under `--output-uri` on the steps that write (`extract-archives`,
  `extract-text`). Default: the `OUTPUT_URI` setting (today's `BLOB_ROOT`) +
  `/<dataset_id>/`, so a dataset in another bucket can write next to its data. Files are named
  by sha256 (`<output uri>/<sha256[:2]>/<sha256[2:4]>/<sha256>`), so identical content is
  stored once. The plan pre-fills it from the dataset's last run.

**A uri is a typed object, not a string.** Readers take a uri and read bytes from it; there
is no "get a local file" step. `universal_pathlib` gives one class for both (`UPath`, on
`fsspec` + `s3fs`; `fsspec` is already installed):

```python
uri = UPath("s3://their-bucket/dump/a.pdf")  # or a local path: same methods
data = uri.read_bytes()
with uri.open("rb") as f:
    ...  # seekable; S3 reads by byte range
for found in UPath("s3://their-bucket/dump/").rglob("*"):
    ...
(output_root / key).write_bytes(data)
```

So `local_path` and `LocalBlobStore` mostly disappear into it. What's left of our own code:
crawling with include / exclude and a progress count, "write under sha256", and the
path-or-bytes choice below. Not worth writing ourselves: S3 listing, range reads, retries and
credentials are the hard part, and `fsspec` already does them.
Credentials: boto3's standard chain via `s3fs`, nothing of ours. Behind a new
`cipher-utils[aws]` extra. (Alternative: `cloudpathlib`, same idea, boto3 directly. Or our
own small `Uri` type. `UPath` is the most pathlib-like; we'd alias it `Uri` so "path" keeps
meaning a local file.)

**Path when local, bytes or a stream when not.** Each reader is handed the uri. If it is
local, the reader gets the path itself (no copy, no read into memory). If it is S3:

| Reader | From S3 | Copy? |
|---|---|---|
| PIL (faces, CLIP, EXIF), pyparse email / calendar | bytes | no |
| xberg (documents) | `ExtractInput(kind="bytes", bytes=…, mime_type=…, filename=…)`; the `mime_type` also replaces today's symlink-for-an-extension trick | no |
| filetyper / magika | `identify_bytes` on the head and tail | no |
| stdlib zip / tar (most archives) | `uri.open("rb")`: seekable, reads only the byte ranges it needs | **no**, even for a 50 GB zip |
| `7zz` (7z / rar / iso / cab …) | a separate program that needs a file path, and its sandbox grants access by path | see below |

**`7zz` on S3** can't read a stream (these formats seek), so it copies the archive to a
temp file and deletes it afterwards. That is the only copy; everything else reads in place.

**Size limits** (new, in `ArchiveLimits`, each also an env var and a step parameter):

- `max_archive_bytes` / `PYARCHIVE_MAX_ARCHIVE_GIB` / `--max-archive-gib`: archives bigger
  than this are not opened; the file shows "skipped: archive larger than N GiB". Today there
  is no limit on the archive itself, only on what it writes.
- For non-archive files read from S3 as bytes (a 3 GB PDF), a `MAX_IN_MEMORY_MIB` setting in
  `cipher-utils`: above it the bytes stream to a temp file and the reader gets that path.

**Staging progress.** `load-files` writes its progress to `enrichment_run.progress`, so the UI
shows a bar: "listed 412,000 · matched 380,500 · typed 120,300". The total isn't known until
the listing ends, so it shows counts until then and a percentage after. Re-running skips
files already staged, so an interrupted crawl resumes.

## 8. uv on every host

- Each host runs `uv sync --frozen` from the same `uv.lock`; `ensure_stage_env` adds extras
  per step. The lock hash is part of the version check (§5).
- Offline hosts: a shared wheelhouse (`--find-links`) or a copied uv cache, with
  `UV_OFFLINE=1`. One script builds the wheelhouse on a connected machine.
- Deploy = `git pull && uv sync --frozen` per host, then restart the worker. The worker
  finishes its current step first (SIGTERM to the worker drains it; a second SIGTERM stops
  the step).

## 9. Postgres

- Plain Postgres, primary + replicas, no Citus. Workers write to the primary through
  pgbouncer in transaction mode. Long GPU steps commit per batch, as now, and hold no idle
  transaction.
- Nothing in the runner needs a session-level feature (no LISTEN/NOTIFY, no session advisory
  locks, no prepared statements across transactions). asyncpg's statement cache must be off
  behind pgbouncer (`statement_cache_size=0`); check that's set where engines are built.
- Replicas serve the UI's read-only progress polling if it ever matters. Not needed now.

## 10. From request to run

1. **Request.** A user asks for a dataset (and, optionally, the analytics they want). Saved
   inside Cipher as a request; this replaces the GitHub issue the wizard files today.
2. **Admin setup.** An admin creates the dataset, grants access (`user_dataset_access`),
   and fills in the staging step: the uri to read (+ include / exclude) and, if not the default, the output uri. Nothing runs before this.
3. **Staging.** The admin starts `load-files` (a one-step plan). It crawls that uri with a
   progress bar and writes `file` rows (§7), then sets `dataset.date_staged`.
4. **Plan, sized to what was staged.** Only now is the real size known, so the plan is built
   from the staged inventory (counts and bytes per filetype group), not guesses:
   - steps that have nothing to do are left off (no images → no face or image steps; no
     `.ics` and no email → no events);
   - each step shows its measured estimate for this many files (`enrichment_run` history,
     per host class) and which pool it runs on; a step with no run history says so;
   - per-file LLM steps show their call count next to the time ("312,000 emails ≈ 41 h on
     the LLM service"), so the admin can narrow them (filetype groups, `--include-bulk` off,
     the event gate) or leave them out. Cipher suggests; the admin decides.
   The user's original request pre-selects steps; the admin adjusts.
5. **Approve** (admins only). Only then can workers claim the steps.
6. **Progress** is the existing pipeline view, plus per step: which host, last heartbeat,
   pause / cancel / resume, the log tail on failure.
7. **Follow-ups** (`resolve-entities`, `link-face-cooccurrence`, `profile-dataset`) are
   **proposed** when a plan finishes, with their estimates, never run automatically.

## 11. Not doing

- Celery, Prefect, Dagster, Ray, Redis. They add infrastructure this deployment doesn't have.
- A separate `llm` pool or host class.
- Containers per step. `CIPHER_STAGE_ENV_ISOLATED=1` stays available if wanted later.
- Auto-scaling. Hosts are fixed; more hosts = start more workers.
- Workers that pick up file batches directly (bypassing `cipher` commands). The command stays
  the unit, so a hand run and a runner run are the same thing.

## 12. Decisions

**Answered (2026-10-12)**

1. **Queue:** hand-rolled on `enrichment_run`. No Procrastinate.
3. **Several hosts on one per-file step:** allowed, one run row per host (§5).
4. **LLM steps at once per service:** 1 by default, set per service in worker settings.
5. **LLM:** always a service on its own GPU machine, called over HTTP from CPU steps; the
   LLM code doesn't change (§3, §6).
8. **Code mismatch:** warn and run; record branch + SHA on every run row. Refusing is a
   worker setting (§5).
9. **Approval:** admins only.
10. **Files:** every location is a uri (directory or `s3://bucket/prefix`). The read uri is a
    `load-files` parameter, crawled with include / exclude and a progress bar; Cipher writes
    only under the output uri. Nothing on the dataset table (§7).
12. **Credentials:** boto3's standard chain for now, nothing custom.
2. **Where a plan lives:** columns on `enrichment_run` (`plan_id`, approver, status
   `requested`), no new table.
6. **Which run claimed each file:** new `enrichment.run_id` column, so a dead host's files go
   back to the queue at once.
7. **Requests stay GitHub issues** (revised 2026-10-12). Users request a dataset or analytics
   as an issue; running is an admin's job, queued from the pipeline. No approval queue in the
   app, no run history (a re-run reuses its row).
13. **Uri type:** `universal_pathlib`, aliased `Uri`.
14. **Readers:** the path when local; bytes or a seekable stream from S3; zip / tar never
    copied. `7zz` copies an S3 archive to a temp file. No S3 mounts.

**Open**

15. **Archive size limit:** `max_archive_bytes` (env + param). Open: its default. Suggest
    none (off) for local files and 50 GiB for S3, where `7zz` must copy.

## 13. Build order (after sign-off)

1. Fix `record_run` for concurrent runs (heartbeat, SIGTERM, adopt `CIPHER_RUN_ID`) and the
   orphan rule. Useful even before the runner: two terminals on one step become safe.
2. Migration: the `enrichment_run` columns, `enrichment.run_id`.
3. Pool/services function next to `ANALYTIC_PARAM_MODELS`, with a test that every command
   has one.
4. `cipher worker --pool cpu|gpu`: claim, run, heartbeat, cancel, drain.
   Two workers on this machine against a test dataset (e.g. `runner-test`) first.
5. API + UI: request, admin setup + staging step form (read uri, include / exclude, output uri), staging step, plan from the staged
   inventory, approve, pause / cancel / resume. The wizard stops filing issues.
6. Files: `Uri` (`universal_pathlib`), path-or-bytes readers, zip / tar over seekable S3
   streams, `max_archive_bytes` + `MAX_IN_MEMORY_MIB`, `7zz` temp copy for S3 archives,
   `load-files <uri>` crawl with include / exclude + progress, `--output-uri` on the writing
   steps.
7. GPU: GPU slots, OCR start/stop in the worker.
8. Docs: `docs/cli.md` (`worker`, `load-files` options), `docs/running-analytics.md`,
   glossary (**run plan**, **pool**, **service**, **output uri**). Rename "blob store" in the glossary and `docs/archive-extraction.md`.

## 14. What was built (2026-10-12)

**Data.** Migration `0055_run_plans`: on `enrichment_run` `plan_id`, `position`, `depends_on`,
`pool`, `services`, `worker`, `note`, `requested_by`, `approved_by`, `code_version`
(`{"approved": …, "ran": …}`), `date_created`, `date_approved`, `date_heartbeat`; on
`enrichment` `run_id`. Also fixed `idx_enrichment_pending`: its predicate used lowercase
statuses while the column stores enum names, so the index never matched.

**Shared schema.** `cipher.schemas.ingestion.run_plan`: step types (every analytic, `staging`,
and the follow-ups `entity_resolution`, `face_cooccurrence`, `dataset_profile`),
`step_requirements` (pool / services / one-per-dataset, from the parameters),
`step_command` (the `cipher` argv), `step_dependencies`, statuses, API models.
`tests/test_run_plan.py` holds every step to a real command.

**Run recording.** `record_run` adopts the plan row named by `CIPHER_RUN_ID`, stamps
`date_heartbeat` every 30 s, tags each claim with its run (`enrichment.run_id`), and closes the
row `stopped` on Ctrl-C / SIGTERM (`cancelled` when it was being cancelled). The orphan rule is
now "the claiming run has no fresh heartbeat (2 min)", so two hosts or terminals can share a
step. The resolution sweep heartbeats too.

**Worker.** `cipher worker --pool cpu|gpu` (`orchestration/worker.py`): claims under one
advisory lock (dependencies done, LLM cap, one-per-dataset steps), runs the command as a
subprocess in its own process group with a log file per step, heartbeats, interrupts on
`cancelling` (SIGINT, then SIGTERM, then SIGKILL after 2 min each), closes the row from the
exit code if the command didn't. When nothing is queued it **joins** a running per-file step
that still has pending files (up to `--max-hosts-per-step`). A lost worker's step is queued
again by the next claim.

**API** (`/runs`, admin-only writes): `POST /runs/plans` queues steps, `GET /runs/plans?datasetId`
(anyone with access), `POST /runs/plans/{id}/cancel`, `POST /runs/{id}/cancel` (also cancels
the queued steps that wait on it), `POST /runs/{id}/requeue` (in place). Requests stay GitHub
issues: `/datasets/requests…`, now part of the one datasets router.

**UI.** All in the dataset page's **enrichment pipeline**, nothing separate: a **Staging** row
first (files, source uri, crawl progress); every row shows its step state (`Queued · after
Text extraction`, `Running on <host> · 3 min`, `Cancelled`, `Failed`) in place of the
estimate; a `⋯` menu on row hover (admin: Stage files…, Run now, Run again, Stop / Cancel;
everyone: Details, Show error); a branch icon with a tooltip when a step ran on another
commit; the section summary counts running and queued steps. Footer: admins `Run selected`
(confirm dialog, queues), everyone else `Request selected` (GitHub issue, as before).

**Files.** `cipher.utils.uri` (`Uri` = `UPath`, `to_uri`, `is_local`, `local_path`,
`read_bytes`, `open_binary`, `local_copy`, `list_files`), `cipher.utils.output.OutputStore`
(was `LocalBlobStore`), `OUTPUT_URI` (was `BLOB_ROOT`). `load-files <uri> --include
--exclude` crawls with 16 files typed at once and writes progress. xberg gets bytes + mime
type for remote files; path-only readers (pytabular, vCard, OCR page rendering, rekey) use
`local_copy`. zip / tar / mbox read S3 archives as seekable streams; `7zz` gets a temp copy;
`max_archive_bytes` (default none local, 50 GiB remote). `universal-pathlib` in
`cipher-utils`, `s3fs` in its `aws` extra (orchestration and backend depend on it).

**Differences from the design.**
- `ocr` is a `gpu` step (it starts its own model), not a CPU step calling an OCR service.
- `depends_on` holds step types of the same plan, not row ids, so a re-run or a joined copy
  of a step counts.
- Requests are GitHub issues, not in-app plans; there is no approval step.
- An S3 file's `path` is `/<bucket>/<key>` (the column needs a leading `/`); `device` is the
  bucket.

**Verified.** `runner-test` dataset: plan (staging with an exclude glob → archive extraction)
created through the API, run by a real `cipher worker --pool cpu`: one row per step, in order,
with host and progress; the zip's members written to `~/data/cipher/output/<dataset id>/`.

**Where a step runs.** The worker writes `enrichment_run.process` (migration
`0056_run_process`) when it starts a step: host, worker pid, the step's pid (its process-group
leader) and its log file (`--log-dir`, default `~/data/cipher/worker-logs/<run id>.log` on that
host). The row menu's **Details** shows them with copyable `tail -f <log>` / `ps -g <pid>`
lines, and `cipher runs [--here]` lists every queued or running step from any machine.
Stopping a step from the app sends it SIGINT (then SIGTERM, then SIGKILL after 2 min each)
and also cancels the queued steps that wait on it. "Run again" re-queues the same row; no run
history is kept beyond the latest row per step (finished rows stay: time estimates are
measured from them).

**Not built yet.** Two steps on one GPU, an offline wheelhouse script, replicas for progress
reads, an S3 run against a real bucket (needs credentials on a host).
