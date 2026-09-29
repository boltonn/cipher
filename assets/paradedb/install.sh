#!/usr/bin/env bash
# Offline install of ParadeDB pg_search for PGDG PostgreSQL 18 on Rocky/RHEL 9 (per paradedb.com/docs/deploy/self-hosted/extension).
# Run as root on EVERY node (primary and replicas).
set -euo pipefail
cd "$(dirname "$0")"
sha256sum -c --quiet SHA256SUMS

if ! rpm -q postgresql18-server >/dev/null 2>&1; then
  echo "postgresql18-server is not installed as an RPM on this host (Postgres may be in a container) - see README.md." >&2
  exit 1
fi
if ! ls /usr/pgsql-18/share/extension/vector.control >/dev/null 2>&1; then
  echo "WARNING: pgvector (pgvector_18) not found; pg_search 0.25+ requires it before CREATE EXTENSION." >&2
fi

yum install -y --disablerepo='*' ./deps/*.rpm ./pg_search_18-*.rpm
ls -l /usr/pgsql-18/lib/pg_search.so
echo "Installed. Next: shared_preload_libraries + restart, then CREATE EXTENSION pg_search CASCADE (see README.md)."
