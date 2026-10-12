# Archive extraction (`pyarchive`)

**Status:** 2026-10-07. Decisions locked (§9). Build steps 1–5 landed (§10); `rag` unpacked 2026-10-10.

**Decision.** A new analytic, `analytics/pyarchive`, turns archive members into
ordinary `file` rows with `parent_id` set to the archive. The orchestration
wraps it as a new enrichment, `archive_extraction`.

- **Bytes go to a content-addressed output store, keyed by sha256.** It is a local directory
  now and S3 later. There is no on-disk tree. `uri` says where the bytes are, and `path`
  says where the file was found.
- **Compression is an encoding, not a container.** `report.csv.gz` is one csv row.
  `logs.tar.gz` is one tar row.
- **zip and the tar family are read in-process with the stdlib.** Everything else (7z,
  rar, iso, cab, ...) goes through the **official 7-Zip `7zz`**, pinned to the latest release,
  running in a **pure-Python sandbox** (Landlock + network namespace + rlimits), with no
  extra tools to install. `7zz` itself is optional.
- **Nested archives go back through the enrichment queue.** The analytic never recurses
  itself. Depth, cycle and duplicate guards run at queue time, and bomb limits run on every
  byte written.
- **Processing is by hash.** An archive whose sha256 was already extracted in the dataset
  is skipped. Every sighting still keeps its own `file` row.

Terminology follows `docs/glossary.md`. Related: `extract_emails.py` (today's
only `parent_id` producer), `docs/enrichments.md`.

---

## 1. What exists today

- `file.parent_id` (FK `file.id`, `ON DELETE CASCADE`, indexed) already links a child
  to its source file. Only email attachments set it.
- **The uniqueness key is `(dataset_id, uri)` with `ON CONFLICT DO NOTHING`.** So the same
  attachment in two emails (same md5 file name in the same folder) keeps **only the
  first** email as parent, and the second sighting is silently dropped. Content-addressed
  bytes would make this the norm, so the key has to change (§3.2).
- **Readers are split between `uri` and `path`.** `fetch_bytes_from_uri` is used by
  faces, image embedding, EXIF, events and email. `Path(resource["path"])` is used by OCR, xberg
  batch extraction and vCard contacts. Bytes that aren't at their `path`, whether a stored file
  or S3, need all of these to resolve through `uri` (§3.3).
- filetyper's `archive` group has 35 types. Many are not containers we'd open
  (`onnx`, `npy`, `h5`, `squashfs`, `snap`, ...). pyarchive keeps its own allowlist.
  Single-stream compressors (`gzip`, `bzip`, `xz`, `zst`, `lz4`) leave the archive
  allowlist entirely (§4).
- `pyparse/parsers/archives/{zip,tar,sevenzip,rar}.py` are legacy, unwired and broken:
  - they call `compute_hash(file_obj, ...)`, which takes a `Path`;
  - even if that worked, hashing drains the stream before `fb.read()`, so the written files would be empty;
  - they write member names unchecked, which allows path traversal;
  - `sevenzip` extracts everything twice.

  **Delete them and the `pyparse[rar,archives]` extras.** mbox is a container too: pyarchive
  splits it into one `.eml` member per message (`backends/mbox.py`), and the broken pyparse
  `MboxParser` is gone.
- Host (Ubuntu 20.04, kernel 5.15): system p7zip 16.02 (old, with unfixed CVEs; don't use
  it). bubblewrap is here only because VS Code depends on it, and **the offline network won't
  have it**, so the sandbox doesn't use it (§2.1).

## 2. Engine: stdlib + sandboxed `7zz`

The goals are newest, most efficient, and least likely to have vulnerabilities.

| | stdlib `zipfile`/`tarfile` | `7zz` (official 7-Zip) | libarchive (`libarchive-c`) |
|---|---|---|---|
| formats | zip, tar + gz/bz2/xz (zstd via extra) | 7z, rar4/5, iso, cab, msi, wim, arj, lzh, xar, dmg, zip variants stdlib can't do (AES, deflate64) | most of both |
| speed | C zlib/lzma/bz2, GIL released | fastest, multithreaded LZMA/LZMA2, official RAR code | C, single-threaded |
| vuln surface | container parsing in memory-safe Python; decoders are the most-audited C there is | C++, and a crash stays inside the sandbox | C, **in our process** (holds DB creds), steady CVE stream in its RAR/7z/zip readers, distro 3.6 lags fixes |
| freshness | ships with Python | we pin and update one static binary, with no distro lag | system lib |

**Chosen: stdlib for zip/tar, sandboxed `7zz` for the rest, no libarchive.** The point
is that a library inside our process can't be contained, and a subprocess can.
`7zz` is **optional to install, never silently skipped**. If it isn't found (`SEVENZIP_PATH`,
`7zz` on `PATH`, `~/.local/share/cipher/bin/7zz`), each archive that needs it fails as
`missing: <what to install>` and the command exits 1 listing it; once it's installed the next
run retries them (§14). The stdlib formats work regardless.

### 2.1 Sandbox: pure Python, no extra tools

Nothing is installed and nothing goes online. The sandbox is three features built into the
Linux kernel, switched on by system calls Python's standard library can already make
(`os.unshare`, `resource.setrlimit`, and three Landlock syscalls through `ctypes`). There is
no package, daemon, root access or network involved -- the same code works on the offline
network as long as its kernel is recent enough.

`7zz` is never started directly. It is started through `python -I .../pyarchive/jail.py --
7zz x ...`, a small stdlib-only launcher that locks *itself* down and then `exec`s `7zz`,
which inherits every restriction (and can't undo them). The launcher is run by file path,
not `-m pyarchive.jail`: importing the package starts magika's threads, and the kernel won't
create a namespace for a multi-threaded process.

| Layer | What it stops | Kernel feature | Needs |
|---|---|---|---|
| **resource limits** | a member growing past `max_member_bytes` (the kernel stops the write), runaway memory, core dumps; `NO_NEW_PRIVS` blocks setuid tricks | `setrlimit`, `prctl` | any Linux |
| **network block** | any connection out (the process gets a network namespace with no interfaces) | unprivileged user + network namespaces | `kernel.unprivileged_userns_clone=1` (the default on Ubuntu/Debian/RHEL 8+); on Ubuntu 24.04+ also `kernel.apparmor_restrict_unprivileged_userns=0` |
| **file access limits** | reading anything but the archive and `/usr/lib/locale`, executing anything but `7zz`, writing anywhere but its scratch dir (so `.env`, `~/.ssh`, the output store and other datasets are out of reach) | Landlock | Linux 5.13+ with `landlock` in `/sys/kernel/security/lsm` (Ubuntu 22.04+ and RHEL 9 ship it on) |

The environment is emptied (no `.env` values or tokens leak in), the process gets its own
session, and passwords reach `7zz` on stdin, never its command line (which other users can
read in `ps`).

**Checking a machine:** `uv run pyarchive sandbox` reports each layer as `ok`, or `NO` with what
goes unprotected without it and the exact fix; it exits 1 if any is missing. The warning an
extraction logs on such a machine says the same, and only appears when 7-Zip actually runs
(7z / rar / iso, or zip members only 7-Zip reads). Each extraction also checks, logs a warning once
per missing layer, and carries on with what it got (`--sandbox best_effort`, the default).
`--sandbox required` makes a missing layer fail the archive instead. `--sandbox off` runs `7zz`
directly, for an environment where the sandbox applies but blocks `7zz` itself (`pyarchive
sandbox` reports that as `7-Zip runs in it  NO`, e.g. a dynamically linked `7zz` that needs libraries the
filesystem layer hides). Off, the size limits still hold: each member is measured as it
finishes and the watcher polls the one in progress, in place of the kernel's `RLIMIT_FSIZE`.
Nothing else needs a sandbox: zip and tar are read in-process by the standard library. Verified on this box (kernel 5.15): all three apply, and a
sandboxed process reading `.env` or writing outside scratch is refused. A stage run in its own
container (`--network none`, read-only root) is already isolated by the container.

7-Zip ≥ 25 refuses dangerous symlink paths by default (the CVE-2025-11001/11002 class), and we
also never follow links when walking the scratch dir.

The stdlib hands a zip's members to `7zz` when their method is one it can't read (AES,
deflate64, ppmd, zstd); without `7zz` the rest of the zip is kept and the archive fails as
`missing: ...` until it's installed.

## 3. Storage and the file row

### 3.1 Blob store

```
<output uri>/<sha256[:2]>/<sha256[2:4]>/<sha256>     # output uri: <OUTPUT_URI>/<dataset id>, a directory or s3://bucket/prefix
```

The member is streamed to a temp file in the output uri, hashing it on the way
(md5 + sha256 + size in one pass), then `os.replace`d onto its key. That's atomic, and if
the key already exists the temp file is just dropped, so identical content is stored once
across every archive and dataset. A `BlobStore` protocol (`put_stream`,
`exists`, `uri_for`, `open`) lives in `cipher-utils`. Local is implemented now. S3 is the other
implementation when it's asked for. Blobs have no extension, so readers get
`mime_type`/`filetype` from the row and never from the name.

### 3.2 Row for an archive member

| field | value |
|---|---|
| `filename` | member basename |
| `path` | **where it was found**: `<archive path>/<member path>`, e.g. `/data/x.zip/docs/a.pdf` |
| `uri` | stored file's uri; many rows may share it |
| `parent_id` | the archive's file id |
| `md5`/`sha256`/`size` | from the write pass |
| `filetype*`/`mime_type` | filetyper on the stored file |
| `date_last_updated`/`date_created` | member mtime / ctime where the format stores them |

`path` is never read as a filesystem path, only displayed. The file browser
already builds its tree from `path`, so an archive shows as a folder with its
internal tree, and that's all the "tree" there is.

**Migration:** the unique key `uq_dataset_uri` → **`uq_dataset_path (dataset_id, path)`**.
Staged disk files map path to uri one-to-one, so they're unaffected. Every sighting is a row, and
a re-run after a crash is an idempotent upsert. Member names are normalized (strip
`/` and drive letters, drop `..`/`.`, empty → `_unnamed_<n>`). Duplicate names inside one
archive get `~2`, `~3`. This is purely for display, because nothing is written under that name.

Email attachments should move to the same model in a later step: blob +
`<email path>/<attachment filename>`. That fixes the dropped second sighting.

### 3.3 Reading by `uri`

`cipher.utils.io` gets one resolver: `local_path(uri) -> Path`. For a `file://` uri
it returns the path. For S3 it downloads into a local cache. `fetch_bytes_from_uri` stays for
in-memory readers. OCR, xberg batch and vCard switch from
`resource["path"]` to `local_path(resource["uri"])`. That's a three-call-site change, and it's
the same change the S3 work needs anyway.

## 4. Compression is an encoding, not a file

People think of `report.csv.gz` as a csv and of `logs.tar.gz` as a tar. Most tools agree.
So:

- **Staging peeks through one compression layer.** When magika says
  `gzip`/`bzip`/`xz`/`zst`/`lz4`, filetyper decompresses up to the first 64 KiB and types
  that instead (`ustar` at offset 257 → `tar`). The row gets the **inner** `filetype` /
  `filetype_group` and a new **`compression`** JSONB column holding `CompressionInfo`
  (`encoding`: a `Compression` StrEnum `gzip`/`bzip2`/`xz`/`zstd`/`lz4`, plus the
  **as-found** `md5`, `sha256`, `size` and, for gzip, the header's `filename` and
  `date_modified`). Staging already hashes the as-found bytes, so it fills these in at no
  extra cost. The UI shows `CSV · gzip`. Filter with `compression->>'encoding'`.
- **A compressed container** (`.tar.gz`, `.tar.zst`, ...) is a tar row with
  `compression=gzip`. Its members get `parent_id` = that row directly, so no
  intermediate `.tar` file ever exists. The row keeps its as-found bytes and hashes.
- **A compressed single file** (`report.csv.gz`) stays one row. `archive_extraction`
  decompresses it into the output store and **updates the same row**: `uri` → the stored file, and
  `md5`/`sha256`/`size` → the content. `path` and `compression` still say how it
  was found. From then on it's an ordinary csv for every analytic, and it dedups against an
  uncompressed copy of the same csv. The as-found hashes stay in `compression`, so
  nothing about the original file is lost. A search by hash checks both.

The rule in one line: **a container keeps its as-found bytes, and a compressed
single file is replaced by its content.** Both are one row.

## 5. Queueing, nesting, guards

```
archive A (pending) ─ extract ─▶ members upserted (parent_id=A)
                                   └─ member B is an allowlisted container ─▶ queue B
```

The workflow drains in passes until nothing is pending. When B is queued, a recursive CTE
over `parent_id` gives:

- **depth.** Rows past `max_depth` (default 5) are `SKIPPED`, `depth`.
- **cycle.** A member's sha256 equal to the archive's own or any ancestor's sha256 means the row
  is written but never queued. This catches `droste.zip`-style quines and A→B→A.
- **duplicate.** Another file in the dataset with the same sha256 is already extracted or queued →
  `SKIPPED`, "same content as file X". The duplicate's row exists, which records the
  sighting. Its contents live under the first copy, and the UI links there.
  Copying child rows from an extraction in another dataset (pure SQL, the stored files already
  exist) is a later optimization.

**Limits** (`ArchiveLimits`, a pydantic model; the CLI options and request params mirror it):

| limit | default | measured on |
|---|---|---|
| `max_total_bytes` | 20 GiB / archive | bytes actually written, never header claims |
| `max_member_bytes` | 8 GiB | written bytes (`RLIMIT_FSIZE` for 7zz) |
| `max_ratio` | 250× once a member passes 64 MiB | written ÷ compressed bytes consumed |
| `max_entries` | 1,000,000 | members seen |
| `max_depth` | 5 | parent chain |
| `min_free_disk` | 10 GiB | `disk_usage(scratch dir)` every 256 MiB |

When a limit trips, the partial member is dropped and the run stops. Members already written stay,
because they're real evidence. The row is `FAILED` with `limit:max_ratio after 1,204 members`.
An archive whose own listing is encrypted, and that no known password opens, is `SKIPPED`,
`encrypted` (§13). A corrupt archive keeps what
was read and is marked `FAILED`.

## 6. Speed

- **One pass per stdlib member.** Decompress → md5 + sha256 → scratch file, in
  1 MiB chunks. `zlib`/`lzma`/`hashlib` release the GIL, so threads really overlap.
- **7zz**: `-mmt` for solid LZMA2. It extracts to sandbox scratch on the
  same filesystem as the output uri. We hash each file once (page-cache hot), then
  `os.replace` it. That's a rename, not a copy.
- **Concurrency.** A thread pool works across archives (`--concurrency`, default 4). Large
  zips fan members out across threads, each with its own `ZipFile` handle. Tar and single
  streams are sequential by nature.
- **Typing.** Magika runs in batches (`identify_paths`) over each flushed group of stored files. Hashes
  come from the write pass, never a second read.
- **DB.** `bulk_upsert_files` per 500 members, with one commit per batch.
- Benchmark before keeping any concurrency (email parsing taught us threads can be
  slower). Use the `cipher benchmark` harness on many small zips plus a few multi-GB
  tar.gz/7z.

### 6.1 Huge files, interruptions, disk and memory (measured 2026-10-07)

| concern | how it's handled | measured |
|---|---|---|
| memory, one huge member | 1 MiB chunks, hashed as they're written, never buffered | 1 GiB member: peak RSS 109 MB (= interpreter baseline), ~185 MB/s with md5+sha256 |
| memory, millions of members | tar's member list cleared per entry; the zip entry count is read from the end record **before** zipfile loads the directory; the name-dedup set is bounded by `max_entries` | 300k-member tar.gz: peak 198 MB, 72 s (~4k tiny files/s, filesystem-bound) |
| killed mid-member | scratch file in `<output uri>/.tmp` (local) or the temp dir (S3); `sweep_tmp()` at run start removes ones older than an hour | — |
| killed mid-archive | rows commit in batches; the re-run passes `skip(member_path)` for recorded members (display paths are deterministic). zip jumps over them, tar reads through without writing or hashing | 300k recorded members: 14 s to skip vs 72 s to extract |
| truncated / corrupt | zip: that member is `corrupt`, the rest still read. tar / single stream: `ArchiveCorruptError` after the members before it (kept) | real `rag`: 1 truncated zip, reported cleanly |
| disk | free space checked before each member (declared size) and every 256 MiB written; `ENOSPC` while writing becomes the `disk` limit, not "corrupt" | — |
| finishing at all | per-archive enrichment row; limits bound the work; throttled progress shows it's moving | — |

## 7. Progress

1. **Archives done / total.** These come from `enrichment` rows, so the existing pipeline view
   works unchanged.
2. **Inside the current archive(s).** `enrichment_run.progress` (JSONB, already added in
   migration 0049 for multi-step sweeps; archives add an `archives` key beside `steps`)
   holds a list of `ArchiveProgress {file_id, filename, members_done, members_total | None,
   bytes_in, bytes_in_total}`, written at most every 2 s on the run recorder's own
   session.
   - `bytes_in` counts compressed bytes consumed: a counting wrapper on the raw
     stream, or `7zz -bsp1` percentages. Its total is the archive's `size`, so tar.gz,
     which has no index, still gets a real percentage.
   - `members_done` comes from the write loop, or from a line count of `7zz -bb1`.
     `members_total` comes from the zip central directory or `7zz l`, and is `None` for tar.
   - CLI: one nested tqdm per worker. UI: the pipeline tooltip shows
     "unpacking `foo.7z`: 41,203 files, 63%".

## 8. Package and pipeline

```
analytics/pyarchive/src/pyarchive/
  __init__.py        # extract(), SUPPORTED_FILETYPES, available_backends()
  schemas.py         # ArchiveMember, ExtractedMember, ArchiveLimits, ArchiveProgress, ArchiveSkipReason
  guard.py           # byte/ratio/entry/disk accounting -> ArchiveLimitError
  names.py           # member path normalization for display paths
  backends/{stdlib,sevenzip}.py
  jail.py            # Landlock + unshare + rlimits launcher, then exec
  cli.py             # `pyarchive extract <file> --output-uri ...` stand-alone
  api/main.py        # optional FastAPI, parity with other analytics
```

The extras are `zstd = ["backports.zstd"]` (the PEP 784 backport, which goes away on Python 3.14),
`lz4 = ["lz4"]`, `fastapi`, and `sevenzip = []` (a binary probe; it never pip-installs anything).
Orchestration gets `archive-extraction = ["pyarchive", "filetyper"]` +
`ensure_stage_env`. Queueing only picks up filetypes an installed backend can
open, and `--filetypes zip,7z` narrows a run.

- `EnrichmentType.ARCHIVE_EXTRACTION` has no prerequisites and **runs before every other
  file enrichment**. Those queue by filter at run start, so they pick up the new members.
  It's the first step after staging in the request wizard.
- An archive attached to an email is queued for it, and an email found in an archive is just an `email` file.
  "Run all" loops while archive or email extraction is pending (zip → eml → zip).
- Glossary: **archive extraction**, **archive member**, **output store**, **compression**
  (an encoding of one file, never a container).
- Frontend: the breadcrumb on a member's page says "Found in `x.zip` › `docs/`". The archive page
  gets a members table, and duplicates get "Same content as `y.zip`".

## 9. Decisions (2026-10-07)

1. **No on-disk tree.** Content-addressed blobs. `path` = where the file was found (display
   only), `uri` = blob. The unique key moves to `(dataset_id, path)`.
2. **Engine:** stdlib in-process for zip/tar, and the official `7zz` in the pure-Python jail for the rest (optional binary).
   No libarchive, py7zr, rarfile, or system p7zip.
3. **Duplicate archives are skipped by sha256**, while every sighting keeps its row.
4. **`enrichment_run.progress` column:** yes.
5. **Compression is an attribute (`file.compression`, JSONB `CompressionInfo` with the
   as-found hashes)**, never a parent/child level (§4).
6. **Exact parent.** `parent_id` is the specific archive row the member was found in. Each
   sighting is its own row (unique on `(dataset_id, path)`).
7. **No bubblewrap on the offline network.** The sandbox is pure Python (Landlock +
   `os.unshare` + rlimits). `7zz` may or may not be present, so it's optional and probed (§2.1).

## 10. Build order

1. ✅ Read files through `uri`: `local_path()` + the three path readers. `BlobStore` (local).
2. ✅ Migration 0050: `uq_dataset_path` + `file.compression` (`enrichment_run.progress` was
   already 0049). filetyper peeks through compression.
3. ✅ pyarchive stdlib backend + guard + names (17 tests; real `rag` archives: 17 zip + 2 tar.gz → 1,979 members in 2 s), with hostile fixtures built in-test: traversal
   names, symlink members, a quine, a ratio bomb, an overlapping-entry zip, duplicate names, an
   encrypted zip, a truncated tar.
4. ✅ `cipher extract-archives` workflow (`rag`: 20 archives → 1,979 members, 1 `.emz` decoded, 1 corrupt): queue CTE, run recorder, progress writes,
   in-place decode of compressed single files.
5. ✅ `7zz` backend + `pyarchive.jail` (Landlock/unshare/rlimits, probe and step-down): 7z, rar, iso, cab, arj, lha, xar, dmg, squashfs.
6. Email attachments onto blobs + `path` = found-at. Cross-queue email ↔ archive. Delete the
   legacy pyparse archive parsers.
7. UI: members table, breadcrumb, progress tooltip. Then benchmark and tune.

## 11. What step 4 found and changed (2026-10-10)

- **xberg types files by extension.** Blobs have none, and xberg's batch API returns a
  failure *as the file's text* (`Error: Validation error: Could not determine MIME type`).
  xberg now gets a temporary symlink with the right suffix (`suffixed_path`: the name's own,
  less a compression suffix once decoded, else the filetype's); no bytes copied. A result
  that is an xberg error is marked failed, never stored. 11 dev-DB rows already held such
  messages as their text (pre-existing).
- **Magika's groups weren't the registry's.** A file typed by the model (no extension,
  e.g. a blob) got magika's group (`eml` -> `text`, `csv` -> `code`); `FileTyper` now
  takes the registry's entry for the label.
- **Bytes-typed zips weren't checked for Office.** Email attachments are typed from bytes,
  which skipped the docx/xlsx/pptx check: 130 of `rag`'s 148 "zips" were Office files.
- **Emails found inside archives** have no folder for their attachments; they went under
  `ATTACHMENTS_DIR/<file id>`. Since 2026-10-12 every email's attachments go into the output store
  with `path` = `<email path>/<filename>` (migration 0054 moved existing rows' paths).
- **Order.** `archive_extraction` is a prerequisite of every analytic that reads files
  (`ENRICHMENT_DEPENDENCIES`), first in the request wizard; `extract-text` unpacks and
  loops emails <-> archives before documents.
- **Not yet:** members skipped inside an archive (encrypted, links, unsupported methods)
  are counted on the run, not recorded as rows (a row needs bytes); the `7zz` backend; the
  UI for in-archive progress (written to `enrichment_run.progress.archives`) and the
  archive members table.

## 12. 7z / rar / iso, encryption, typing order (2026-10-10)

- **7zz.** The official static build (`7zzs` from the ip7z/7zip release, installed as
  `~/.local/share/cipher/bin/7zz`; else `SEVENZIP_PATH` or `7zz` on `PATH`). Verify the
  release's sha256 when copying it to the offline network. Without it those filetypes fail
  as `missing` (§14). Members stream: `7zz x -bb1` prints `- <path>` per file, the
  previous one moves into the store (a rename: scratch lives in `<output uri>/.tmp`) while
  the next decodes. Limits: `RLIMIT_FSIZE` per member, a watcher plus a per-member check for
  archive total / expansion ratio (archive-level: solid blocks hide per-file packed sizes) / disk.
- **Jail** (`pyarchive/jail.py`, run by file path so it imports only the stdlib -- importing
  the package starts magika threads and `unshare` refuses a multi-threaded process):
  rlimits + `NO_NEW_PRIVS`, `unshare(NEWUSER|NEWNET)`, Landlock (read the archive and
  `/usr/lib/locale`, execute 7zz, write only scratch). `/proc` stays hidden (it would expose
  other processes' environments), so the thread count is passed (`-mmt`). Verified here: all
  three layers apply; reading `.env` or writing outside scratch fails. `--sandbox required`
  fails such archives on a machine where a layer can't apply.
- **`file.is_encrypted`** (migration 0051). Set by filetyper (zip member flags, PDF
  `/Encrypt` -- includes permissions-only PDFs that open without a password -- and encrypted
  Office packages) and by extraction: a 7z / rar with an encrypted listing is `skipped:
  encrypted` with the archive flagged; an encrypted zip member becomes a row whose blob is its
  ciphertext as found, flagged; an encrypted 7z / rar member (no bytes without a password) is
  counted on the run and flags its archive. `rag`: 4 PDFs.
- **Typing order** (corrected): heuristics on the file's real name first, magika only to
  refine generic text (`analytics/filetyper/README.md`). Members are typed with their member
  filename, not the blob path. `rag` retype: 634 macOS AppleDouble files (`._name`, now a
  registry magic number) had been called `appleplist`; `.txt` that is really python / csv /
  html refined.
- **Open (closed in §13):** passwords; zip members whose method only 7zz reads; the members
  / in-archive progress UI.

## 13. Passwords, zip fallback, encryption meaning, UI (2026-10-12)

- **What `is_encrypted` means:** reading this file's bytes needs a password. A PDF locked
  only against editing or printing opens without one, so it isn't (filetyper asks pdfium,
  the `pdf` extra; `rag`'s 4 flagged PDFs were all of that kind and are cleared). An archive
  is flagged when it holds encrypted members, whether or not we had the password. A member
  we decrypted is stored decrypted and is not flagged; a member no password opens is **not
  stored** (its ciphertext was useless to every later step) -- it's counted as
  `member_skip:encrypted` and its archive is flagged. Re-typing (`rekey --filetypes`) leaves the
  flag alone for 7z / rar / iso and the other formats only an archive reader can check.
- **Passwords file:** `ARCHIVE_PASSWORDS_FILE` (default `~/data/cipher/archive-passwords.txt`,
  or `--passwords-file`), one password per line, tried in order. Keep it `chmod 600`. zip
  (ZipCrypto) is tried in-process; 7z / rar / AES zip go through `7zz`: plain members first
  with no password, then each password on the members still locked (an encrypted listing is
  opened by the first password that works). When the file is newer than an archive's last
  extraction, archives with encrypted members (and `skipped: encrypted` ones) are queued again
  and only what's still missing is extracted.
- **zip fallback:** members the stdlib can't read (AES, deflate64, ...) are re-read by `7zz`
  from the same zip, matched by member path.
- **Resume through 7zz** no longer re-extracts recorded members: they're left out of the
  `7zz x` member list (`-spd @list`) instead of extracted and thrown away.
- **Per-member errors from 7zz:** errors go to stdout (`-bse1`), where each one follows its
  member's line, so a CRC failure marks that member `corrupt` instead of storing bad bytes.
- **UI:** in the dataset file tree an unpacked archive opens like a folder (`memberCount` on
  browse rows; the folder its members' paths imply is no longer listed separately). File
  details and the file page link to the archive or email a file was found in, and show its
  compression and encryption. While an unpack runs, the pipeline view shows two stages:
  archives, and members of the archive in progress.
- **Fixed:** every unpacked archive was flagged `is_encrypted` (a `Counter` holding a 0 is
  still truthy). Only the throwaway test dataset had been affected.

## 14. A missing tool is an error, never a skip (2026-10-12)

User rule: if something isn't installed, say what is needed instead of quietly doing less.

- **What can be missing:** `7zz` (7z / rar / iso / cab / ..., and AES / deflate64 zip
  members), the zstd and lz4 decoders (`.zst`, `.lz4`, `.tar.zst`: the `zstd` / `lz4` extras).
  Every archive filetype is queued whatever is installed (`archive_filetypes()`).
- **What happens:** the archive is `FAILED` with `missing: <filetype> needs <what to install
  and where>`; members already read stay. At the end `extract-archives` (and `extract-text`)
  print `ERROR: N archive(s) not unpacked: ...` per missing tool and exit 1.
- **After installing:** nothing to reset. Every run first puts `missing:` failures back in the
  queue, so the next `extract-archives` unpacks them.
- **Sandbox (`best_effort`):** a layer this machine can't apply is a warning in plain words --
  what goes unprotected and the command to fix it (`pyarchive sandbox` lists the same);
  `required` makes it an error; `off` runs 7zz bare.
- **Encrypted files** are never handed to an analytic that can't read them: queueing records
  them `SKIPPED`, `encrypted: needs a password to read` (archive extraction excepted, it tries
  passwords). `rekey --filetypes` re-queues a file whose encryption flag changed.
- **Encrypted email** (filetyper): S/MIME enveloped `.eml` (`application/pkcs7-mime`, not
  `signed-data`, else the CMS content type decides), PGP/MIME (`multipart/encrypted`), inline
  PGP; also `.p7m` (CMS EnvelopedData) and OpenPGP messages (`.gpg` / armored). Outlook `.msg`
  is flagged by pyparse when the email is parsed (message class `IPM.Note.SMIME`, read from its
  OLE property stream) -- exact and free there, where filetyper would have to scan raw bytes.
  pyparse's verdict on any email is copied onto the file row. Who sets `is_encrypted` follows
  speed and dependencies: whichever step already reads the format sets it. The email is still parsed -- headers need no key -- and its
  encrypted body becomes a flagged `smime.p7m` child that no analytic reads. Not detected:
  Microsoft IRM / rights-protected (`.rpmsg`) mail.
- **filetyper without pypdfium2** (`pdf` extra): warns once, saying what is lost -- it can't tell a PDF
  that needs a password from one only locked against editing, so every PDF with `/Encrypt` is flagged
  (the cipher stage envs install it).

## 15. Output store and remote archives (2026-10-12, docs/pipeline-runner.md)

- **"Blob store" is now the output store** (`cipher.utils.output.OutputStore`, `StoredFile`;
  `ExtractedMember.stored`). It writes under an **output uri**: a directory or
  `s3://bucket/prefix`, default `<OUTPUT_URI>/<dataset id>/` (`OUTPUT_URI` replaces
  `BLOB_ROOT`; `--output-uri` on `extract-archives` / `extract-text`). Keys are unchanged.
  On S3 each file is written to a local scratch file while hashed, then uploaded; the disk
  guard watches the scratch disk.
- **Remote archives:** `extract()` takes a local path or a `Uri`. zip / tar / mbox and decoding
  read an S3 archive as a seekable stream (only the byte ranges they need); `7zz` gets a temp
  copy (`local_copy`), deleted afterwards.
- **Archive size limit:** `ArchiveLimits.max_archive_bytes` / `PYARCHIVE_MAX_ARCHIVE_GIB` /
  `--max-archive-gib`. An archive bigger than it isn't opened (`limit:archive_bytes`). Default:
  none for a local file, 50 GiB for a remote one (what a `7zz` copy could cost).
