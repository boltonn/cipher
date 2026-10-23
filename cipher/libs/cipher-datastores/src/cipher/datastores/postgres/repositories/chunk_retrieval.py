"""Postgres implementation of `ChunkRetrievalRepository`.

One `chunk` table (text + embedding + optional `text_tsv`) joined to `mention`
for entity/graph filtering, so keyword + semantic + entity + multi-hop graph is a
single SQL query grouped by file. See docs/retrieval-architecture.md /
docs/retrieval-workflow.md.

Keyword ranking is `RETRIEVAL__TEXT_RANKER`:
  - `pg_search`  -> ParadeDB BM25 (`|||`) with an ICU tokenizer  [default]
  - `core`       -> `text_tsv @@ to_tsquery(...)`, `ts_rank_cd`, accent-insensitive (`unaccent`)
`pgroonga` / `pg_bigm` are recognised but fall through to `core` here until their
index paths are added. A ranker whose extension isn't installed downgrades a rung
(`effective_text_ranker`), so search works on plain Postgres.
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
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas._base.common import PaginatedResponse
from cipher.schemas.content.document import ScoredDocumentTextChunk
from cipher.schemas.content.email import ScoredEmailTextChunk
from cipher.schemas.content.results import FileSearchResult, MonthCount, PaginatedFileSearchResponse, ResultShape
from cipher.schemas.content.search import (
    SUMMARY_CHUNK_INDEX,
    ChunkSortField,
    MentionSpan,
    RetrievalMode,
    RetrievalQuery,
    TextChunk,
    chunk_id_for,
)

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
# Keyword `total` counts files over at most this many matching chunks: exact below it, a floor
# above it. An uncapped count grows with how common the term is (813 ms p50 at 875k chunks).
_KEYWORD_COUNT_CAP = 5_000
# Keyword ranker -> (Postgres extension it needs, ranker it downgrades to without it).
_RANKER_LADDER: dict[str, tuple[str, str]] = {
    "pg_search": ("pg_search", "pgroonga"),
    "pgroonga": ("pgroonga", "bigm"),
    "bigm": ("pg_bigm", "core"),
}
# Configured ranker -> the one this database supports; resolved once per process.
_effective_rankers: dict[str, str] = {}


def effective_text_ranker(configured: str, *, installed: set[str]) -> str:
    """The keyword ranker that actually runs: each rung missing its extension downgrades one rung."""
    ranker = configured
    while ranker in _RANKER_LADDER and _RANKER_LADDER[ranker][0] not in installed:
        ranker = _RANKER_LADDER[ranker][1]
    return ranker


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
        is_summary=bool(row.get("is_summary")),
        generated_by=row.get("generated_by"),
        date_created=row["date_created"],
        score=score,
        mention_spans=mention_spans,
    )
    if row["filetype_group"] == "email":
        return ScoredEmailTextChunk(**common, **{k: v for k, v in meta.items() if k not in common})
    doc_meta = {k: v for k, v in meta.items() if k not in common and k not in {"tables", "document_structure"}}
    doc_meta.setdefault("filename", meta.get("title") or row["file_id"])  # extracted_text may be absent
    return ScoredDocumentTextChunk(**common, **doc_meta)


def _result_shape(rows) -> ResultShape:
    """Content-date histogram and `filetype_group` mix of the candidate pool, counted per file."""
    months: dict[str, set[str]] = {}
    groups: dict[str, set[str]] = {}
    for row in rows:
        groups.setdefault(row["filetype_group"], set()).add(row["file_id"])
        if row["date_content"] is not None:
            months.setdefault(row["date_content"].strftime("%Y-%m"), set()).add(row["file_id"])
    return ResultShape(
        date_histogram=[MonthCount(month=month, files=len(files)) for month, files in sorted(months.items())],
        filetype_groups={group: len(files) for group, files in groups.items()},
        sample_size=len(rows),
    )


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
        self._group_files: list[list[str]] = []

    # ---- lifecycle -------------------------------------------------------

    async def _resolve_ranker(self) -> None:
        """Downgrade the configured ranker to one the database's installed extensions support."""
        if self.text_ranker not in _effective_rankers:
            rows = await self.session.execute(sa_text("SELECT extname FROM pg_extension"))
            _effective_rankers[self.text_ranker] = effective_text_ranker(
                self.text_ranker, installed={row[0] for row in rows}
            )
        self.text_ranker = _effective_rankers[self.text_ranker]

    def _tsv_sql(self, *, text_param: str) -> str:
        """SQL for `text_tsv`: only the core ranker (and the rungs that fall through to it) reads it."""
        return "NULL" if self.text_ranker == "pg_search" else f"to_tsvector('simple', unaccent(:{text_param}))"

    async def _index_exists(self, name: str) -> bool:
        row = await self.session.execute(sa_text("SELECT 1 FROM pg_class WHERE relname = :n"), {"n": name})
        return row.first() is not None

    async def drop_search_indexes(self) -> None:
        """Drop the HNSW / tsvector / BM25 indexes before a bulk embed (rebuilt by `ensure_schema`)."""
        for name in _SEARCH_INDEXES:
            await self.session.execute(sa_text(f"DROP INDEX IF EXISTS {name}"))
        await self.session.commit()

    async def ensure_schema(self) -> None:
        """Create the vector / full-text search indexes on `chunk` if missing, and backfill `text_tsv` (idempotent)."""
        await self._resolve_ranker()
        if not await self._index_exists(_HNSW_INDEX):
            await self.session.execute(
                sa_text(
                    f"CREATE INDEX {_HNSW_INDEX} ON chunk USING hnsw (embedding vector_cosine_ops) "
                    "WITH (m = 16, ef_construction = 64)"
                )
            )
            await self.session.commit()
            logger.info(f"created HNSW index {_HNSW_INDEX}")

        if self.text_ranker != "pg_search":
            filled = await self.session.execute(
                sa_text("UPDATE chunk SET text_tsv = to_tsvector('simple', unaccent(text)) WHERE text_tsv IS NULL")
            )
            await self.session.commit()
            if filled.rowcount:
                logger.info(f"backfilled text_tsv on {filled.rowcount} chunks for the {self.text_ranker} ranker")

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
                _effective_rankers["pg_search"] = "core"
                self.text_ranker = "core"
                await self.ensure_schema()

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
        await self._resolve_ranker()
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
                "is_summary": c.is_summary,
                "generated_by": c.generated_by,
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
                "chunk_index,start_offset,end_offset,text,is_summary,generated_by,language,embedding,date_content,text_tsv) VALUES "
                "(:id,:dataset_id,:file_id,:sha256,:filetype_group,CAST(:duplicate_file_ids AS jsonb),"
                ":chunk_index,:start_offset,:end_offset,:text,:is_summary,:generated_by,:language,:embedding,"
                f":date_content,{self._tsv_sql(text_param='text')}) "
                "ON CONFLICT (id) DO UPDATE SET "
                f"text=EXCLUDED.text, text_tsv=EXCLUDED.text_tsv, {embedding_set_clause}language=EXCLUDED.language, "
                "generated_by=EXCLUDED.generated_by, "
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
        """Delete the text chunks a file owns as representative (its summary is kept). Caller commits."""
        res = await self.session.execute(
            sa_text("DELETE FROM chunk WHERE file_id = :f AND NOT is_summary"), {"f": file_id}
        )
        return res.rowcount or 0

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete every text chunk in a dataset; summaries (an LLM call each) survive (standalone -- commits)."""
        res = await self.session.execute(
            sa_text("DELETE FROM chunk WHERE dataset_id = :d AND NOT is_summary"), {"d": dataset_id}
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

    async def summary_for(self, *, dataset_id: str, sha256: str) -> TextChunk | None:
        """The dataset's summary chunk for this content, if one was written."""
        row = (
            (
                await self.session.execute(
                    sa_text(
                        "SELECT id, dataset_id, file_id, sha256, filetype_group, duplicate_file_ids, text, "
                        "generated_by, date_created FROM chunk "
                        "WHERE dataset_id = :d AND sha256 = :s AND is_summary LIMIT 1"
                    ),
                    {"d": dataset_id, "s": sha256},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return TextChunk(
            id=row["id"],
            dataset_id=row["dataset_id"],
            file_id=row["file_id"],
            sha256=row["sha256"],
            duplicate_file_ids=row["duplicate_file_ids"] or [],
            filetype=row["filetype_group"],
            chunk_index=SUMMARY_CHUNK_INDEX,
            start_offset=0,
            end_offset=0,
            text=row["text"],
            is_summary=True,
            generated_by=row["generated_by"],
            date_created=row["date_created"],
        )

    async def upsert_summary(
        self,
        *,
        dataset_id: str,
        file_id: str,
        sha256: str,
        filetype_group: str,
        duplicate_file_ids: list[str],
        text: str,
        generated_by: str | None,
        embedding: list[float] | None = None,
    ) -> str:
        """Write (or replace) the dataset's summary chunk for this content. Returns its id. Caller commits."""
        chunk_id = chunk_id_for(dataset_id=dataset_id, sha256=sha256, chunk_index=SUMMARY_CHUNK_INDEX, start_offset=0)
        await self._resolve_ranker()
        await self.session.execute(
            sa_text(
                "INSERT INTO chunk (id,dataset_id,file_id,sha256,filetype_group,duplicate_file_ids,chunk_index,"
                "start_offset,end_offset,text,is_summary,generated_by,embedding,text_tsv) VALUES (:id,:d,:f,:s,:g,"
                f"CAST(:dups AS jsonb),:i,0,0,:t,true,:m,CAST(:e AS vector),{self._tsv_sql(text_param='t')}) "
                "ON CONFLICT (id) DO UPDATE SET text=EXCLUDED.text, text_tsv=EXCLUDED.text_tsv, "
                "generated_by=EXCLUDED.generated_by, "
                "embedding=EXCLUDED.embedding, duplicate_file_ids=EXCLUDED.duplicate_file_ids, date_created=now()"
            ),
            {
                "id": chunk_id,
                "d": dataset_id,
                "f": file_id,
                "s": sha256,
                "g": filetype_group,
                "dups": json.dumps(duplicate_file_ids),
                "i": SUMMARY_CHUNK_INDEX,
                "t": text,
                "m": generated_by,
                "e": str(list(embedding)) if embedding else None,
            },
        )
        return chunk_id

    async def any_summary(self, sha256: str) -> tuple[str, str | None, list[float]] | None:
        """(text, model, embedding) of this content's summary in any dataset -- reused instead of a new LLM call."""
        row = (
            await self.session.execute(
                sa_text(
                    "SELECT text, generated_by, embedding::text AS embedding FROM chunk "
                    "WHERE sha256 = :s AND is_summary ORDER BY embedding IS NULL LIMIT 1"
                ),
                {"s": sha256},
            )
        ).one_or_none()
        if row is None:
            return None
        embedding = [float(x) for x in row.embedding.strip("[]").split(",")] if row.embedding else []
        return row.text, row.generated_by, embedding

    async def summaries_missing_embedding(self, dataset_id: str, limit: int = 500) -> list[tuple[str, str]]:
        """(chunk id, text) of a dataset's summary chunks not embedded yet."""
        rows = await self.session.execute(
            sa_text("SELECT id, text FROM chunk WHERE dataset_id = :d AND is_summary AND embedding IS NULL LIMIT :n"),
            {"d": dataset_id, "n": limit},
        )
        return [(r.id, r.text) for r in rows]

    async def set_embedding(self, chunk_id: str, embedding: list[float]) -> None:
        """Fill one chunk's embedding. Caller commits."""
        await self.session.execute(
            sa_text("UPDATE chunk SET embedding = CAST(:e AS vector) WHERE id = :i"),
            {"e": str(list(embedding)), "i": chunk_id},
        )

    async def spans_for_file(self, file_id: str) -> list[ChunkSpan]:
        """Every chunk id + span for a file (through `duplicate_file_ids`), by offset."""
        rows = (
            await self.session.execute(
                sa_text(
                    "SELECT id, start_offset, end_offset FROM chunk "
                    "WHERE NOT is_summary AND (file_id = :f OR duplicate_file_ids @> to_jsonb(cast(:f as text))) "
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
            (
                await self.session.execute(
                    sa_text(
                        "SELECT id, dataset_id, file_id, sha256, filetype_group, duplicate_file_ids, "
                        "chunk_index, start_offset, end_offset, text, language, embedding::text AS embedding "
                        "FROM chunk WHERE file_id = :f AND NOT is_summary ORDER BY chunk_index"
                    ),
                    {"f": file_id},
                )
            )
            .mappings()
            .all()
        )
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
        for index, files in enumerate(self._group_files):
            # File-level like `mention_values`: most of a person's mentions are email headers (no chunk).
            p[f"group_files_{index}"] = files
            parts.append(f"c.file_id = ANY(cast(:group_files_{index} AS text[]))")
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
        # What the data itself says (GIN-indexed copies of the extracted-text metadata).
        for column, include, exclude in (
            ("source_tags", f.source_tags, f.exclude_source_tags),
            ("message_states", f.message_states, f.exclude_message_states),
        ):
            if include:
                p[column] = list(include)
                out.append(
                    f"EXISTS (SELECT 1 FROM file fl WHERE fl.id = c.file_id AND fl.{column} ?| cast(:{column} as text[]))"
                )
            if exclude:
                p[f"exclude_{column}"] = list(exclude)
                out.append(
                    f"NOT EXISTS (SELECT 1 FROM file fl WHERE fl.id = c.file_id "
                    f"AND fl.{column} ?| cast(:exclude_{column} as text[]))"
                )
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
                out.append(f"EXISTS (SELECT 1 FROM mention m WHERE m.chunk_id = c.id AND m.{field} = ANY(:{key}))")
        return out

    def _keyword_predicate(self, p: dict, *, exact: bool) -> str:
        """Words matched as typed: any of them (BM25-ranked), or all of them in order when `exact`."""
        if self.text_ranker == "pg_search":
            return "c.text ### :kw" if exact else "c.text ||| :kw"
        p["kw_tsq"] = p["kw"]
        return f"c.text_tsv @@ {self._tsquery(exact=exact)}"

    def _keyword_score(self, *, exact: bool) -> str:
        if self.text_ranker == "pg_search":
            return "paradedb.score(c.id)"
        return f"ts_rank_cd(c.text_tsv, {self._tsquery(exact=exact)})"

    @staticmethod
    def _tsquery(*, exact: bool) -> str:
        return (
            f"{'phraseto' if exact else 'plainto'}_tsquery(coalesce(:kw_lang,'simple')::regconfig, unaccent(:kw_tsq))"
        )

    async def _resolve_expand(self, q: RetrievalQuery) -> None:
        """Walk the graph from the seeds, then resolve to the files that involve the expansion.

        A file involves an entity when it mentions it in the text or has it as an email's
        sender/recipient (header mentions carry no chunk_id, so matching is at file level).
        `seed_names` add the files that mention those names, resolved or not.
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
        files = set(rows.scalars().all())
        for name in g.seed_names:
            files |= set(await self.mentions.file_ids_for_values(dataset_id=q.filters.dataset_id, values=[name]))
        self._expand_files = list(files)

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
        await self._resolve_ranker()
        await self._resolve_expand(query)
        self._value_files = None
        if query.filters.mention_values:
            self._value_files = await self.mentions.file_ids_for_values(
                dataset_id=query.filters.dataset_id,
                values=query.filters.mention_values,
                provenance=query.filters.mention_provenance,
            )
        self._group_files = [
            await self.mentions.file_ids_for_entities(dataset_id=query.filters.dataset_id, entity_ids=group)
            for group in query.filters.entity_groups or []
        ]
        # asyncpg reuses prepared statements; after 5 runs Postgres switches to a generic plan,
        # which keeps the dataset filter out of the pg_search scan (~8x slower, 37 -> 293 ms).
        await self.session.execute(sa_text("SET LOCAL plan_cache_mode = force_custom_plan"))
        p: dict = {}
        has_text = bool(query.text and query.text.strip())
        has_vec = query.embedding is not None
        mode = RetrievalMode.KEYWORD if query.exact_match and has_text else query.mode
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
            cand = (
                f"SELECT c.id, {self._keyword_score(exact=query.exact_match)} AS score FROM chunk c "
                f"WHERE {scope} AND {self._keyword_predicate(p, exact=query.exact_match)} ORDER BY score DESC LIMIT :pool"
            )
        elif mode == RetrievalMode.SEMANTIC:
            cand = (
                f"SELECT c.id, 1 - (c.embedding <=> CAST(:qvec AS vector)) AS score FROM chunk c "
                f"WHERE {scope} AND c.embedding IS NOT NULL "
                f"ORDER BY c.embedding <=> CAST(:qvec AS vector) LIMIT :pool"
            )
        else:  # hybrid RRF of the two candidate orderings
            sem = (
                f"SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> CAST(:qvec AS vector)) AS r FROM chunk c "
                f"WHERE {scope} AND c.embedding IS NOT NULL ORDER BY c.embedding <=> CAST(:qvec AS vector) LIMIT :pool"
            )
            if has_text:
                kw = (
                    f"SELECT id, row_number() OVER (ORDER BY s DESC) AS r FROM ("
                    f"  SELECT c.id, {self._keyword_score(exact=query.exact_match)} AS s FROM chunk c "
                    f"  WHERE {scope} AND {self._keyword_predicate(p, exact=query.exact_match)} ORDER BY s DESC LIMIT :pool) k"
                )
                cand = (
                    f"SELECT COALESCE(kw.id, sem.id) AS id, "
                    f"COALESCE(1.0/({_RRF_K}+kw.r),0) + COALESCE(1.0/({_RRF_K}+sem.r),0) AS score "
                    f"FROM ({kw}) kw FULL OUTER JOIN ({sem}) sem ON kw.id = sem.id"
                )
            else:
                cand = (
                    f"SELECT c.id, 1 - (c.embedding <=> CAST(:qvec AS vector)) AS score FROM chunk c "
                    f"WHERE {scope} AND c.embedding IS NOT NULL "
                    f"ORDER BY c.embedding <=> CAST(:qvec AS vector) LIMIT :pool"
                )

        # Stage B -- refine candidates by the mention/graph filters (plain joins, no
        # pg_search). Already applied directly for browse -- don't re-filter (and
        # don't re-add duplicate bind params).
        mention_parts = [] if browse else self._mention_sql(query, p)
        refine_where = (" WHERE " + " AND ".join(mention_parts)) if mention_parts else ""

        sql = (
            f"WITH cand AS ({cand}), "
            f"refined AS (SELECT cand.id, cand.score FROM cand JOIN chunk c ON c.id = cand.id{refine_where}) "
            "SELECT c.id, c.dataset_id, c.file_id, c.sha256, c.duplicate_file_ids, c.filetype_group, "
            "c.chunk_index, c.start_offset, c.end_offset, c.text, c.is_summary, c.generated_by, "
            "c.date_created, c.date_content, refined.score AS score "
            "FROM refined JOIN chunk c ON c.id = refined.id "
            "ORDER BY refined.score DESC"
        )
        rows = (await self.session.execute(sa_text(sql), p)).mappings().all()

        # group by file, rank files by best chunk score
        by_file: dict[str, list[dict]] = {}
        for r in rows:
            by_file.setdefault(r["file_id"], []).append(dict(r))
        ordered_files = sorted(by_file.items(), key=lambda kv: max(c["score"] for c in kv[1]), reverse=True)
        if query.sort_by == ChunkSortField.DATE and not browse:
            # The best `pool` matches, newest content first; undated last (browse is already in date order).
            def newest(kv):
                dates = [c["date_content"] for c in kv[1] if c["date_content"] is not None]
                return (bool(dates), max(dates, default=None) or datetime.min.replace(tzinfo=UTC))

            ordered_files.sort(key=newest, reverse=True)
        total = len(ordered_files)
        total_is_exact = browse or (mode == RetrievalMode.KEYWORD and has_text)
        if mode == RetrievalMode.KEYWORD and has_text and (refine_where or len(rows) >= pool):
            # The pool didn't hold every match: count files with a keyword match that pass the
            # filters, over the first `_KEYWORD_COUNT_CAP` matches. Otherwise `total` is already exact.
            p["count_cap"] = _KEYWORD_COUNT_CAP
            matched_chunks, total = (
                await self.session.execute(
                    sa_text(
                        f"WITH matched AS (SELECT c.id, c.file_id FROM chunk c WHERE {scope} "
                        f"AND {self._keyword_predicate(p, exact=query.exact_match)} LIMIT :count_cap) "
                        f"SELECT (SELECT count(*) FROM matched), count(DISTINCT matched.file_id) FROM matched "
                        f"JOIN chunk c ON c.id = matched.id{refine_where}"
                    ),
                    p,
                )
            ).one()
            total_is_exact = matched_chunks < _KEYWORD_COUNT_CAP
        elif browse:
            # The pool is the newest `pool` *chunks*, so counting its files undercounts;
            # count every file the filters admit instead.
            total = (
                await self.session.execute(
                    sa_text(
                        f"SELECT count(*) FROM (SELECT DISTINCT c.file_id FROM chunk c WHERE {browse_where}) files"
                    ),
                    p,
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
        # Files with no extracted text (tables, found through their summary chunk) still need a name.
        names = await self.session.execute(
            sa_text("SELECT id, filename, filetype FROM file WHERE id = ANY(cast(:file_ids AS text[]))"),
            {"file_ids": [file_id for file_id, _ in page_files]},
        )
        for file_id, filename, filetype in names.all():
            meta_by_file[file_id] = {"filename": filename, "filetype": filetype, **meta_by_file.get(file_id, {})}

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
        file_rows = await self.session.execute(
            sa_text("SELECT id, tags, source_tags, message_states FROM file WHERE id = ANY(cast(:file_ids AS text[]))"),
            {"file_ids": [r.file_id for r in results]},
        )
        by_file = {row.id: row for row in file_rows.all()}
        for result in results:
            if row := by_file.get(result.file_id):
                result.tags, result.source_tags, result.message_states = row.tags, row.source_tags, row.message_states
        return PaginatedFileSearchResponse(
            total=total,
            total_is_exact=total_is_exact,
            page=query.page,
            limit=query.limit,
            data=results,
            shape=_result_shape(rows) if query.include_shape else None,
        )

    # ---- legacy request-model shims (so existing /search routes are untouched) ----

    async def search_text(self, request) -> PaginatedResponse:
        """`ChunkTextSearchRequest` -> `search(mode=keyword)`."""
        return await self.search(
            RetrievalQuery(
                mode=RetrievalMode.KEYWORD,
                text=request.query,
                exact_match=request.exact_match,
                filters=request.filters,
                graph_expand=request.graph_expand,
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
                graph_expand=request.graph_expand,
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
                graph_expand=request.graph_expand,
                min_similarity=request.min_similarity,
                page=request.page,
                limit=request.limit,
                sort_order=request.sort_order,
            )
        )
