# assets

Offline artifacts for air-gapped installs.

## `paradedb/` — pg_search (ParadeDB BM25) for PostgreSQL 18 on Rocky/RHEL 9 x86_64

Follows ParadeDB's [self-hosted extension guide](https://www.paradedb.com/docs/deploy/self-hosted/extension).

- `pg_search_18-0.25.10-1PARADEDB.el9.x86_64.rpm` comes from the
  [v0.25.10 release](https://github.com/paradedb/paradedb/releases/tag/v0.25.10), and its sha256 matches the release digest.
- `deps/` holds `openblas-serial` + `libgfortran`/`libquadmath` from Rocky 9 AppStream/BaseOS. `pg_search.so` links
  `libopenblas.so.0`, and without it **Postgres will not start** once pg_search is preloaded.

Requirements on each node: Postgres from the PGDG RPMs (`postgresql18-server`), plus `pgvector` (`pgvector_18`).
pg_search 0.25+ needs pgvector.

### Multi-node (primary + streaming replicas)

1. **Every node**, as root: `./paradedb/install.sh`. It checks the sha256 sums and runs a
   `yum install` with every repo disabled, so it works offline.
2. **Every node**: add it to `postgresql.conf`, keeping whatever is already in the list:
   ```ini
   shared_preload_libraries = 'pg_search'        # e.g. 'pg_stat_statements,pg_search'
   ```
   On the **replicas**, ParadeDB also requires:
   ```ini
   hot_standby_feedback = on
   primary_slot_name = '<slot>'                  # a physical slot created on the primary
   ```
3. Restart the replicas, then the primary (`systemctl restart postgresql-18`). A reload is not enough.
4. **Primary only** (it replicates), in the cipher DB:
   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_search CASCADE;
   SELECT extname, extversion FROM pg_extension WHERE extname IN ('pg_search', 'vector');
   ```
5. Set `RETRIEVAL__TEXT_RANKER=pg_search` for the backend, then check that `GET /api/search/config` shows
   `textRankerEffective: "pg_search"`.

### Postgres in a Docker container

The RPM cannot go into a container. Whoever owns the container needs to swap the image for
`paradedb/paradedb` (PG 18), which already ships pg_search, or install ParadeDB's Debian `.deb` for the image's
Debian release (see the guide above). Copying `pg_search.so` in by hand needs `libopenblas.so.0` in the image,
and it is lost when the container is recreated.

## `models/nerd-canon-v3/` — nerd canonical NER model (xlm-roberta, fp32, 2.2GB)

The weights live at **https://huggingface.co/nazgul44/nerd-canon-v3** (private). This folder only holds
the small config files, the expected sha256, and the downloader:

```bash
HF_TOKEN=hf_xxx ./models/nerd-canon-v3/download.sh   # fetches weights + tokenizer, checks sha256
export NERD_MODEL_DIR=$PWD/models/nerd-canon-v3
```
