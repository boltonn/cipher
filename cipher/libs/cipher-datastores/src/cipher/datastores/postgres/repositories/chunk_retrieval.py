"""Postgres implementation of `ChunkRetrievalRepository`.

One `chunk` table (text + embedding + optional `text_tsv`) joined to `mention`
for entity/graph filtering, so keyword + semantic + entity + multi-hop graph is a
single SQL query grouped by file. See docs/retrieval-architecture.md /
docs/retrieval-workflow.md.

Keyword ranking is `RETRIEVAL__TEXT_RANKER`:
  - `pg_search`  -> ParadeDB BM25 (`@@@`) with an ICU tokenizer  [default]
  - `core`       -> `text_tsv @@ to_tsquery(...)`, `ts_rank_cd`
`pgroonga` / `pg_bigm` are recognised but fall through to `core` here until their
index paths are added.
"""

import json
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.base.retrieval import ChunkRetrievalRepository, ChunkSpan
from cipher.datastores.postgres.repositories.mention import (
    PostgresMentionRepository,
    correspondence_predicates,
)
from cipher.datastores.postgres.repositories.tag import PostgresTagRepository
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas._base.common import PaginatedResponse
from cipher.schemas.content.document import ScoredDocumentTextChunk
from cipher.schemas.content.email import ScoredEmailTextChunk
from cipher.schemas.content.results import FileSearchResult, PaginatedFileSearchResponse
from cipher.schemas.content.search import MentionSpan, RetrievalMode, RetrievalQuery, TextChunk

_BM25_INDEX = "ix_chunk_text_bm25"
_HNSW_INDEX = "ix_chunk_embedding_hnsw"
_TSV_INDEX = "ix_chunk_text_tsv"
# Search indexes are dropped before a bulk embed and rebuilt after -- HNSW and
# pg_search both maintain internal structures that don't survive a killed write
# mid-load, and per-batch maintenance is slow. The plain btree/PK indexes stay.
_SEARCH_INDEXES = (_BM25_INDEX, _HNSW_INDEX, _TSV_INDEX)
_RRF_K = 60
_MAX_CHUNKS_PER_FILE = 50
# Candidate pool for semantic / hybrid ranking before grouping by file -- mirrors
# ES kNN `num_candidates`. `total` for those modes is a floor over this pool.
_MIN_POOL = 500


def _as_utc(value: datetime | None) -> datetime | None:
    """Content dates are parsed naive from metadata; store them as UTC."""
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _scored_chunk(row: dict, meta: dict, score: float, mention_spans: list[MentionSpan]):
    """Rebuild a Scored{Document,Email}TextChunk from a `chunk` row + `extracted_text.metadata`."""
    common = dict(
        id=row["id"],
        dataset_id=row["dataset_id"],
        file_id=row["file_id"],
        sha256=row["sha256"],
        duplicate_file_ids=row["duplicate_file_ids"] or [],
        filetype=meta.get("filetype") or row["filetype_group"],
        chunk_index=row["chunk_index"],
        start_offset=row["start_offset"],
        end_offset=row["end_offset"],
        text=row["text"],
        date_created=row["date_created"],
        score=score,
        mention_spans=mention_spans,
    )
    if row["filetype_group"] == "email":
        return ScoredEmailTextChunk(**common, **{k: v for k, v in meta.items() if k not in common})
    doc_meta = {k: v for k, v in meta.items() if k not in common and k not in {"tables", "document_structure"}}
    doc_meta.setdefault("filename", meta.get("title") or row["file_id"])  # extracted_text may be absent
    return ScoredDocumentTextChunk(**common, **doc_meta)


class PostgresChunkRetrievalRepository(ChunkRetrievalRepository):
    def __init__(
        self,
        session: AsyncSession,
        *,
        text_ranker: str = "pg_search",
        graph_repo=None,
        graph_expand_entity_cap: int = 10_000,
    ):
        self.session = session
        self.text_ranker = text_ranker
        self.graph_repo = graph_repo
        self.graph_expand_entity_cap = graph_expand_entity_cap
        self.mentions = PostgresMentionRepository(session=session)
        self._value_files: list[str] | None = None

    # ---- lifecycle -------------------------------------------------------

    async def _index_exists(self, name: str) -> bool:
        row = await self.session.execute(sa_text("SELECT 1 FROM pg_class WHERE relname = :n"), {"n": name})
        return row.first() is not None

    async def drop_search_indexes(self) -> None:
        """Drop the HNSW / tsvector / BM25 indexes before a bulk embed (rebuilt by `ensure_schema`)."""
        for name in _SEARCH_INDEXES:
            await self.session.execute(sa_text(f"DROP INDEX IF EXISTS {name}"))
        await self.session.commit()

    async def ensure_schema(self) -> None:
        """Create the vector / full-text search indexes on `chunk` if missing (idempotent)."""
        if not await self._index_exists(_HNSW_INDEX):
            await self.session.execute(
                sa_text(
                    f"CREATE INDEX {_HNSW_INDEX} ON chunk USING hnsw (embedding vector_cosine_ops) "
                    "WITH (m = 16, ef_construction = 64)"
                )
            )
            await self.session.commit()
            logger.info(f"created HNSW index {_HNSW_INDEX}")

        if not await self._index_exists(_TSV_INDEX):
            await self.session.execute(sa_text(f"CREATE INDEX {_TSV_INDEX} ON chunk USING gin (text_tsv)"))
            await self.session.commit()
            logger.info(f"created GIN index {_TSV_INDEX}")

        if self.text_ranker == "pg_search" and not await self._index_exists(_BM25_INDEX):
            try:
                await self.session.execute(
                    sa_text(
                        f"CREATE INDEX {_BM25_INDEX} ON chunk USING bm25 "
                        "(id, text, dataset_id, filetype_group, file_id, language) "
                        "WITH (key_field='id', text_fields='"
                        '{"text": {"tokenizer": {"type": "icu"}}}\')'
                    )
                )
                await self.session.commit()
                logger.info(f"created BM25 index {_BM25_INDEX} (pg_search, icu tokenizer)")
            except Exception as exc:  # noqa: BLE001 -- pg_search may be absent; search downgrades to core
                await self.session.rollback()
                logger.warning(f"could not create BM25 index ({exc.__class__.__name__}); keyword search uses core FTS")
                self.text_ranker = "core"

    # ---- writes --------------------------------------------------------

    async def upsert_chunks(self, chunks: list[TextChunk], *, include_embedding: bool = True) -> tuple[int, int]:
        """Insert/replace `chunk` rows keyed by `TextChunk.id`.

        `include_embedding=False` writes identity + span + text only, leaving
        `embedding` untouched -- for `upsert_chunk_spans` (the elasticsearch
        backend's use of this table as the mention join anchor only; the
        embedding already lives in ES and doesn't need a second, expensive copy
        here).
        """
        if not chunks:
            return 0, 0
        rows = [
            {
                "id": c.id,
                "dataset_id": c.dataset_id,
                "file_id": c.file_id,
                "sha256": c.sha256,
                "filetype_group": getattr(c, "filetype_group", "document"),
                "duplicate_file_ids": json.dumps(c.duplicate_file_ids or [c.file_id]),
                "chunk_index": c.chunk_index,
                "start_offset": c.start_offset,
                "end_offset": c.end_offset,
                "text": c.text,
                "language": getattr(c, "detected_language", None),
                "embedding": (str(list(c.embedding)) if c.embedding else None) if include_embedding else None,
                "title": getattr(c, "title", None) or getattr(c, "subject", None),
                "date_content": _as_utc(getattr(c, "date_sent", None) or getattr(c, "date_content_created", None)),
            }
            for c in chunks
        ]
        embedding_set_clause = "embedding=EXCLUDED.embedding, " if include_embedding else ""
        await self.session.execute(
            sa_text(
                "INSERT INTO chunk (id,dataset_id,file_id,sha256,filetype_group,duplicate_file_ids,"
                "chunk_index,start_offset,end_offset,text,language,embedding,date_content) VALUES "
                "(:id,:dataset_id,:file_id,:sha256,:filetype_group,CAST(:duplicate_file_ids AS jsonb),"
                ":chunk_index,:start_offset,:end_offset,:text,:language,:embedding,:date_content) "
                "ON CONFLICT (id) DO UPDATE SET "
                f"text=EXCLUDED.text, {embedding_set_clause}language=EXCLUDED.language, "
                "date_content=EXCLUDED.date_content, "
                "end_offset=EXCLUDED.end_offset, "
                # union, not replace: content-identical files in a dataset upsert the
                # same chunk id (deterministic), each contributing its own file_id
                "duplicate_file_ids=(SELECT COALESCE(jsonb_agg(DISTINCT v), '[]'::jsonb) "
                "FROM jsonb_array_elements_text(chunk.duplicate_file_ids || EXCLUDED.duplicate_file_ids) v)"
            ),
            [{k: v for k, v in r.items() if k != "title"} for r in rows],
        )
        return len(rows), 0

    async def upsert_chunk_spans(self, chunks: list[TextChunk]) -> tuple[int, int]:
        """Write identity + span + text only (no embedding) -- see `upsert_chunks`."""
        return await self.upsert_chunks(chunks, include_embedding=False)

    # Alias so this repo is a drop-in for `ElasticsearchTextChunkRepository` in the embed pipeline.
    async def bulk_index(self, chunks: list[TextChunk], show_progress: bool = False) -> tuple[int, int]:
        """Alias for `upsert_chunks` (embed-pipeline drop-in)."""
        return await self.upsert_chunks(chunks)

    async def list_by_file_id(self, file_id: str, limit: int = 500) -> list[TextChunk]:
        """Alias for `chunks_for_file` (embed-pipeline drop-in for cross-dataset clone)."""
        return await self.chunks_for_file(file_id)

    async def delete_by_file_id(self, file_id: str) -> int:
        """Delete the chunks a file owns as representative. Caller commits."""
        res = await self.session.execute(
            sa_text("DELETE FROM chunk WHERE file_id = :f"), {"f": file_id}
        )
        return res.rowcount or 0

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete every chunk in a dataset (standalone -- commits)."""
        res = await self.session.execute(
            sa_text("DELETE FROM chunk WHERE dataset_id = :d"), {"d": dataset_id}
        )
        await self.session.commit()
        return res.rowcount or 0

    async def attach_duplicate(self, *, dataset_id: str, sha256: str, file_id: str) -> bool:
        """Add `file_id` to the `duplicate_file_ids` of this content's chunks. Caller commits."""
        res = await self.session.execute(
            sa_text(
                "UPDATE chunk SET duplicate_file_ids = "
                "  CASE WHEN duplicate_file_ids @> to_jsonb(cast(:f as text)) THEN duplicate_file_ids "
                "       ELSE duplicate_file_ids || to_jsonb(cast(:f as text)) END "
                "WHERE dataset_id = :d AND sha256 = :s"
            ),
            {"f": file_id, "d": dataset_id, "s": sha256},
        )
        return (res.rowcount or 0) > 0

    async def spans_for_file(self, file_id: str) -> list[ChunkSpan]:
        """Every chunk id + span for a file (through `duplicate_file_ids`), by offset."""
        rows = (
            await self.session.execute(
                sa_text(
                    "SELECT id, start_offset, end_offset FROM chunk "
                    "WHERE file_id = :f OR duplicate_file_ids @> to_jsonb(cast(:f as text)) "
                    "ORDER BY start_offset"
                ),
                {"f": file_id},
            )
        ).all()
        return [ChunkSpan(chunk_id=r.id, start_offset=r.start_offset, end_offset=r.end_offset) for r in rows]

    async def chunks_for_file(self, file_id: str) -> list[TextChunk]:
        """A file's chunks with text + embedding, in reading order.

        For the embed pipeline's cross-dataset content dedup (clone another
        dataset's already-computed embeddings). Not part of the search path.
        """
        rows = (
            await self.session.execute(
                sa_text(
                    "SELECT id, dataset_id, file_id, sha256, filetype_group, duplicate_file_ids, "
                    "chunk_index, start_offset, end_offset, text, language, embedding::text AS embedding "
                    "FROM chunk WHERE file_id = :f ORDER BY chunk_index"
                ),
                {"f": file_id},
            )
        ).mappings().all()
        out: list[TextChunk] = []
        for r in rows:
            emb = r["embedding"]
            out.append(
                TextChunk(
                    id=r["id"],
                    dataset_id=r["dataset_id"],
                    file_id=r["file_id"],
                    sha256=r["sha256"],
                    duplicate_file_ids=r["duplicate_file_ids"] or [r["file_id"]],
                    filetype=r["filetype_group"],
                    chunk_index=r["chunk_index"],
                    start_offset=r["start_offset"],
                    end_offset=r["end_offset"],
                    text=r["text"],
                    embedding=[float(x) for x in emb.strip("[]").split(",")] if emb else [],
                )
            )
        return out

    # ---- search -------------------------------------------------------

    def _index_scope(self, q: RetrievalQuery, p: dict) -> str:
        """Cheap equality filters safe to run alongside the primary index (incl. pg_search)."""
        f = q.filters
        parts = ["true"]
        if f.dataset_id:
            parts.append("c.dataset_id = :dataset_id")
            p["dataset_id"] = f.dataset_id
        if f.dataset_ids is not None:
            parts.append("c.dataset_id = ANY(cast(:dataset_ids AS text[]))")
            p["dataset_ids"] = f.dataset_ids
        if f.filetype_group:
            parts.append("c.filetype_group = :ftg")
            p["ftg"] = f.filetype_group
        if f.file_id:
            parts.append("(c.file_id = :fid OR c.duplicate_file_ids @> to_jsonb(cast(:fid as text)))")
            p["fid"] = f.file_id
        parts.extend(correspondence_predicates(f, p, file_column="c.file_id", date_column="c.date_content"))
        if f.mention_values:
            # Pre-resolved like `_expand_files`; file-level so header/metadata mentions (no chunk) count.
            p["value_files"] = self._value_files or []
            parts.append("c.file_id = ANY(cast(:value_files AS text[]))")
        if q.graph_expand and self._expand_files is not None:
            # Pre-resolved file ids (see `_resolve_expand`): pg_search rejects the
            # equivalent `IN (SELECT ... FROM mention)` once the expansion grows.
            p["expand_files"] = self._expand_files
            parts.append("c.file_id = ANY(cast(:expand_files AS text[]))")
        return " AND ".join(parts)

    def _file_sql(self, q: RetrievalQuery, p: dict) -> list[str]:
        """Filters on the chunk's file -- `filetype` and the content's tags live on `file`, not `chunk`."""
        f = q.filters
        out: list[str] = []
        if f.filetype:
            p["ftype"] = f.filetype
            out.append("EXISTS (SELECT 1 FROM file fl WHERE fl.id = c.file_id AND fl.filetype = :ftype)")
        if f.tags:
            # GIN-indexed `file.tags`: tags are on the content, so every copy of a file carries them.
            p["tags"] = list(f.tags)
            out.append("EXISTS (SELECT 1 FROM file fl WHERE fl.id = c.file_id AND fl.tags ?| cast(:tags as text[]))")
        return out

    def _mention_sql(self, q: RetrievalQuery, p: dict) -> list[str]:
        f = q.filters
        out: list[str] = self._file_sql(q, p)
        if f.entity_ids:
            p["entity_ids"] = list(f.entity_ids)
            out.append(
                "NOT EXISTS (SELECT unnest(cast(:entity_ids as text[])) EXCEPT "
                "SELECT m.entity_id FROM mention m WHERE m.chunk_id = c.id AND m.entity_id IS NOT NULL)"
            )
        for field, vals in (
            ("entity_type", f.entity_types),
            ("selector_type", f.selector_types),
            ("selector_subtype", f.selector_subtypes),
        ):
            if vals:
                key = f"m_{field}"
                p[key] = [v.upper() for v in vals]  # mention enum cols store member NAMES
                out.append(
                    f"EXISTS (SELECT 1 FROM mention m WHERE m.chunk_id = c.id AND m.{field} = ANY(:{key}))"
                )
        return out

    def _keyword_predicate(self, p: dict) -> str:
        if self.text_ranker == "pg_search":
            return "c.text @@@ :kw"
        p["kw_tsq"] = p["kw"]
        return "c.text_tsv @@ plainto_tsquery(coalesce(:kw_lang,'simple'), :kw_tsq)"

    def _keyword_score(self) -> str:
        return "paradedb.score(c.id)" if self.text_ranker == "pg_search" else (
            "ts_rank_cd(c.text_tsv, plainto_tsquery(coalesce(:kw_lang,'simple'), :kw_tsq))"
        )

    async def _resolve_expand(self, q: RetrievalQuery) -> None:
        """Walk the graph from the seeds, then resolve to the files that involve the expansion.

        A file involves an entity when it mentions it in the text or has it as an email's
        sender/recipient (header mentions carry no chunk_id, so matching is at file level).
        """
        self._expand_ids = None
        self._expand_files = None
        if not q.graph_expand or self.graph_repo is None:
            return
        g = q.graph_expand
        ids = set(g.seed_entity_ids)
        for seed in g.seed_entity_ids:
            graph = await self.graph_repo.traverse(
                start_entity_id=seed,
                max_depth=g.max_depth,
                min_weight=g.min_weight,
                relationship_types=g.relationship_types,
                limit=self.graph_expand_entity_cap,
            )
            ids |= {n.id for n in graph.nodes}
        self._expand_ids = list(ids)[: self.graph_expand_entity_cap]
        params = {"ids": self._expand_ids, "dataset_id": q.filters.dataset_id}
        dataset_filter = "AND dataset_id = :dataset_id" if q.filters.dataset_id else ""
        rows = await self.session.execute(
            sa_text(
                "SELECT DISTINCT file_id FROM mention WHERE file_id IS NOT NULL "
                f"AND entity_id = ANY(cast(:ids AS text[])) {dataset_filter}"
            ),
            params,
        )
        self._expand_files = list(rows.scalars().all())

    async def _mention_spans(
        self, *, chunk_ids: list[str], entity_ids: list[str] | None, mention_values: list[str] | None
    ) -> dict[str, list[MentionSpan]]:
        """The filtered entities'/values' mention offsets per chunk -- the "why it matched" marks.

        Matched by offset containment rather than `mention.chunk_id`, which is unset until backfilled.
        """
        if not chunk_ids or not (entity_ids or mention_values):
            return {}
        rows = await self.session.execute(
            sa_text(
                "SELECT DISTINCT c.id, m.entity_id, m.normalized_value, m.start_offset, m.end_offset "
                "FROM chunk c JOIN mention m ON m.file_id = c.file_id AND m.mentioned_type = 'EXTRACTED_TEXT' "
                "AND m.start_offset >= c.start_offset AND m.start_offset < c.end_offset "
                "WHERE c.id = ANY(cast(:chunk_ids as text[])) AND m.end_offset IS NOT NULL "
                "AND (m.entity_id = ANY(cast(:entity_ids as text[])) "
                "OR m.normalized_value = ANY(cast(:values as text[]))) ORDER BY m.start_offset"
            ),
            {
                "chunk_ids": chunk_ids,
                "entity_ids": list(entity_ids or []),
                "values": [*(mention_values or []), *(normalize_name(v) for v in mention_values or [])],
            },
        )
        entity_set = set(entity_ids or [])
        spans: dict[str, list[MentionSpan]] = {}
        for chunk_id, entity_id, normalized_value, start_offset, end_offset in rows.all():
            spans.setdefault(chunk_id, []).append(
                MentionSpan(
                    entity_id=entity_id if entity_id in entity_set else None,
                    normalized_value=None if entity_id in entity_set else normalized_value,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
            )
        return spans

    async def search(self, query: RetrievalQuery) -> PaginatedResponse:
        """Rank chunks (keyword / semantic / hybrid / browse), filter, group by file."""
        await self._resolve_expand(query)
        self._value_files = None
        if query.filters.mention_values:
            self._value_files = await self.mentions.file_ids_for_values(
                dataset_id=query.filters.dataset_id,
                values=query.filters.mention_values,
                provenance=query.filters.mention_provenance,
            )
        p: dict = {}
        has_text = bool(query.text and query.text.strip())
        has_vec = query.embedding is not None
        mode = query.mode
        if mode == RetrievalMode.KEYWORD and not has_text:
            mode = RetrievalMode.SEMANTIC if has_vec else RetrievalMode.HYBRID  # browse
        if mode in (RetrievalMode.SEMANTIC, RetrievalMode.HYBRID) and not has_vec:
            mode = RetrievalMode.KEYWORD if has_text else RetrievalMode.KEYWORD

        if has_text:
            p["kw"] = query.text.strip()
            p["kw_lang"] = query.query_language
        if has_vec:
            p["qvec"] = str(list(query.embedding))  # pgvector accepts '[...]'::vector via asyncpg
        pool = max(_MIN_POOL, (query.offset + query.limit) * 10)
        p["pool"] = pool
        scope = self._index_scope(query, p)
        if has_vec:
            # HNSW otherwise stops at `hnsw.ef_search` (40) rows, starving the pool
            # and any filter applied alongside it; iterative scan (pgvector 0.8+)
            # keeps walking the graph until LIMIT is met.
            await self.session.execute(sa_text("SET LOCAL hnsw.iterative_scan = relaxed_order"))

        # Stage A -- candidates (id, score). Only index-safe scope filters here:
        # pg_search rejects a custom-scan query with correlated mention subqueries.
        # Browse is the one exception: there's no @@@/kNN predicate to protect, so
        # the mention/graph filters would apply directly rather than after a
        # date-limited pool (picking the pool by recency *before* filtering by
        # entity would almost never intersect with that entity's, usually older,
        # mentions) -- BUT applying them as a correlated EXISTS/EXCEPT clause
        # against the *whole* dataset-scoped table doesn't scale (it's fine once
        # Stage A has already narrowed to `pool` rows, which is why the same
        # clause is cheap in Stage B below). So for browse, resolve the filter to
        # a concrete chunk-id list first -- one index-driven scan of `mention`,
        # bounded by the entity's/expansion's mention count, not the corpus size
        # -- the same approach the elasticsearch adapter uses.
        browse = not has_text and not has_vec
        if browse:
            f = query.filters
            browse_ids = None
            if f.entity_ids or f.entity_types or f.selector_types or f.selector_subtypes:
                # Not `pool`: this resolves the *whole* matching set (up to the
                # cap) so the subsequent ORDER BY date DESC LIMIT pool picks the
                # true most-recent matches -- capping at `pool` here first would
                # silently return an arbitrary (not most-recent) slice for an
                # entity with more mentions than the candidate pool size.
                browse_ids = await self.mentions.chunk_ids_for_filter(
                    dataset_id=f.dataset_id,
                    entity_ids=f.entity_ids,
                    entity_types=f.entity_types,
                    selector_types=f.selector_types,
                    selector_subtypes=f.selector_subtypes,
                    limit=self.graph_expand_entity_cap,
                )
            browse_where = " AND ".join([scope, *self._file_sql(query, p)])
            if browse_ids is not None:
                p["browse_ids"] = browse_ids
                browse_where += " AND c.id = ANY(cast(:browse_ids as text[]))"
            # Newest content first (email date_sent / document authored date), not ingest time.
            cand = (
                f"SELECT c.id, (:pool - row_number() OVER (ORDER BY c.date_content DESC NULLS LAST, "
                f"c.date_created DESC))::float AS score FROM chunk c WHERE {browse_where} "
                f"ORDER BY c.date_content DESC NULLS LAST, c.date_created DESC LIMIT :pool"
            )
        elif mode == RetrievalMode.KEYWORD:
            cand = f"SELECT c.id, {self._keyword_score()} AS score FROM chunk c " \
                   f"WHERE {scope} AND {self._keyword_predicate(p)} ORDER BY score DESC LIMIT :pool"
        elif mode == RetrievalMode.SEMANTIC:
            cand = f"SELECT c.id, 1 - (c.embedding <=> CAST(:qvec AS vector)) AS score FROM chunk c " \
                   f"WHERE {scope} AND c.embedding IS NOT NULL " \
                   f"ORDER BY c.embedding <=> CAST(:qvec AS vector) LIMIT :pool"
        else:  # hybrid RRF of the two candidate orderings
            sem = f"SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> CAST(:qvec AS vector)) AS r FROM chunk c " \
                  f"WHERE {scope} AND c.embedding IS NOT NULL ORDER BY c.embedding <=> CAST(:qvec AS vector) LIMIT :pool"
            if has_text:
                kw = (
                    f"SELECT id, row_number() OVER (ORDER BY s DESC) AS r FROM ("
                    f"  SELECT c.id, {self._keyword_score()} AS s FROM chunk c "
                    f"  WHERE {scope} AND {self._keyword_predicate(p)} ORDER BY s DESC LIMIT :pool) k"
                )
                cand = (
                    f"SELECT COALESCE(kw.id, sem.id) AS id, "
                    f"COALESCE(1.0/({_RRF_K}+kw.r),0) + COALESCE(1.0/({_RRF_K}+sem.r),0) AS score "
                    f"FROM ({kw}) kw FULL OUTER JOIN ({sem}) sem ON kw.id = sem.id"
                )
            else:
                cand = f"SELECT c.id, 1 - (c.embedding <=> CAST(:qvec AS vector)) AS score FROM chunk c " \
                       f"WHERE {scope} AND c.embedding IS NOT NULL " \
                       f"ORDER BY c.embedding <=> CAST(:qvec AS vector) LIMIT :pool"

        # Stage B -- refine candidates by the mention/graph filters (plain joins, no
        # pg_search). Already applied directly for browse -- don't re-filter (and
        # don't re-add duplicate bind params).
        mention_parts = [] if browse else self._mention_sql(query, p)
        refine_where = (" WHERE " + " AND ".join(mention_parts)) if mention_parts else ""

        sql = (
            f"WITH cand AS ({cand}), "
            f"refined AS (SELECT cand.id, cand.score FROM cand JOIN chunk c ON c.id = cand.id{refine_where}) "
            "SELECT c.id, c.dataset_id, c.file_id, c.sha256, c.duplicate_file_ids, c.filetype_group, "
            "c.chunk_index, c.start_offset, c.end_offset, c.text, c.date_created, refined.score AS score "
            "FROM refined JOIN chunk c ON c.id = refined.id "
            "ORDER BY refined.score DESC"
        )
        rows = (await self.session.execute(sa_text(sql), p)).mappings().all()

        # group by file, rank files by best chunk score
        by_file: dict[str, list[dict]] = {}
        for r in rows:
            by_file.setdefault(r["file_id"], []).append(dict(r))
        ordered_files = sorted(
            by_file.items(), key=lambda kv: max(c["score"] for c in kv[1]), reverse=True
        )
        total = len(ordered_files)
        total_is_exact = browse or (mode == RetrievalMode.KEYWORD and has_text)
        if mode == RetrievalMode.KEYWORD and has_text:
            # every file with a keyword match that passes the filters, not just the ranked pool's
            total = (
                await self.session.execute(
                    sa_text(
                        f"WITH matched AS (SELECT c.id, c.file_id FROM chunk c WHERE {scope} "
                        f"AND {self._keyword_predicate(p)}) "
                        f"SELECT count(*) FROM (SELECT DISTINCT matched.file_id FROM matched "
                        f"JOIN chunk c ON c.id = matched.id{refine_where}) files"
                    ),
                    p,
                )
            ).scalar_one()
        elif browse:
            # The pool is the newest `pool` *chunks*, so counting its files undercounts;
            # count every file the filters admit instead.
            total = (
                await self.session.execute(
                    sa_text(f"SELECT count(*) FROM (SELECT DISTINCT c.file_id FROM chunk c WHERE {browse_where}) files"), p
                )
            ).scalar_one()
        page_files = ordered_files[query.offset : query.offset + query.limit]
        mention_spans = await self._mention_spans(
            chunk_ids=[cr["id"] for _, chunk_rows in page_files for cr in chunk_rows],
            entity_ids=query.filters.entity_ids,
            mention_values=query.filters.mention_values,
        )
        # Display metadata for the page's files only -- the JSONB is large (tables, document structure),
        # so detoasting it for the whole candidate pool cost more than the search itself.
        meta_rows = await self.session.execute(
            sa_text(
                "SELECT file_id, metadata - 'tables' - 'document_structure' AS meta FROM extracted_text "
                "WHERE file_id = ANY(cast(:file_ids AS text[]))"
            ),
            {"file_ids": [file_id for file_id, _ in page_files]},
        )
        meta_by_file = {file_id: meta or {} for file_id, meta in meta_rows.all()}

        results: list[FileSearchResult] = []
        for file_id, chunk_rows in page_files:
            if browse and query.filters.mention_values:
                # A value filter matches whole files: show the passages holding the value, or the
                # opening chunk when it's only in a header / metadata field.
                chunk_rows = [cr for cr in chunk_rows if cr["id"] in mention_spans] or [
                    min(chunk_rows, key=lambda c: c["chunk_index"])
                ]
            chunk_rows.sort(key=lambda c: -c["score"])
            top = chunk_rows[0]
            capped = sorted(chunk_rows[:_MAX_CHUNKS_PER_FILE], key=lambda c: c["chunk_index"])
            scored = [
                _scored_chunk(cr, meta_by_file.get(file_id, {}), cr["score"], mention_spans.get(cr["id"], []))
                for cr in capped
            ]
            results.append(
                FileSearchResult(
                    file_id=file_id,
                    top_score=float(top["score"]),
                    top_chunk_id=top["id"],
                    match_count=len(chunk_rows),
                    chunks=scored,
                )
            )
        tags = await PostgresTagRepository(self.session).file_tags([r.file_id for r in results])
        for result in results:
            result.tags = tags.get(result.file_id, [])
        return PaginatedFileSearchResponse(
            total=total, total_is_exact=total_is_exact, page=query.page, limit=query.limit, data=results
        )

    # ---- legacy request-model shims (so existing /search routes are untouched) ----

    async def search_text(self, request) -> PaginatedResponse:
        """`ChunkTextSearchRequest` -> `search(mode=keyword)`."""
        return await self.search(
            RetrievalQuery(
                mode=RetrievalMode.KEYWORD,
                text=request.query,
                filters=request.filters,
                page=request.page,
                limit=request.limit,
                sort_order=request.sort_order,
            )
        )

    async def search_semantic(self, request) -> PaginatedResponse:
        """`ChunkSemanticSearchRequest` -> `search(mode=semantic)`."""
        return await self.search(
            RetrievalQuery(
                mode=RetrievalMode.SEMANTIC,
                embedding=list(request.embedding),
                filters=request.filters,
                min_similarity=request.min_similarity,
                page=request.page,
                limit=request.limit,
                sort_order=request.sort_order,
            )
        )

    async def search_hybrid(self, request) -> PaginatedResponse:
        """`ChunkHybridSearchRequest` -> `search(mode=hybrid)`."""
        return await self.search(
            RetrievalQuery(
                mode=RetrievalMode.HYBRID,
                text=request.query,
                embedding=list(request.embedding),
                filters=request.filters,
                min_similarity=request.min_similarity,
                page=request.page,
                limit=request.limit,
                sort_order=request.sort_order,
            )
        )
