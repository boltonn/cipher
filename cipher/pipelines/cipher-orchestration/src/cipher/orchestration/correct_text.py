"""Correct a file's extracted text (OCR mistakes) on every copy of its content.

Text is keyed by content: every file with the same sha256 holds the same text, and
chunks are shared on that assumption, so a correction rewrites all of them together.
A correction only moves what points into the text (`TextCorrection`); nothing is
re-run unless the admin asks for it:

- mentions on untouched text keep their place at new offsets, re-checked against the new text;
- a mention whose words were corrected takes the new spelling (its entity link is cleared
  when that changes its name key); one whose words are gone is deleted (both listed by the dry run);
- prechunked page spans and search chunks keep their ids and embeddings, with offsets and
  text carried across (so keyword search and highlighting see the new text);
- `rerun` picks steps that already read the old text to redo (`restage`): text embedding
  is rebuilt now, the others are cleared and put back to pending.

Refused (nothing written) while a step that reads the text is running on these files.
All in one transaction. The text is flagged `is_content_corrected`, so no pipeline
re-run overwrites it.
"""

from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update

from cipher.datastores.postgres.repositories import (
    PostgresEntityRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
)
from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.utils import normalize_name
from cipher.orchestration.embed_text import _build_chunk, _spans_for
from cipher.orchestration.extract_documents import DEFAULT_CHUNK_SIZE
from cipher.orchestration.extract_entities import _context
from cipher.orchestration.restage import REBUILT_IN_PLACE, restage_text_readers, text_change_impact
from cipher.schemas.content.extraction import ExtractedText, PrechunkedSpan
from cipher.schemas.content.text_correction import (
    CorrectedMention,
    SpanFate,
    TextCorrection,
    TextCorrectionSummary,
)
from cipher.schemas.graph.mention import MentionedType
from cipher.schemas.graph.ontology import SelectorType
from cipher.schemas.ingestion.enrichment import EnrichmentType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cipher.datastores.base.retrieval import ChunkRetrievalRepository
    from cipher.schemas.content.search import TextChunk

EmbedPassages = Callable[[list[str]], Awaitable[list[list[float]]]]


def normalized_value_for(*, surface_text: str, selector_type: SelectorType | None) -> str:
    """The name-group / selector key a mention's text joins -- the same folding the extractors apply."""
    if selector_type is not None:
        from pyselectors.normalize import normalize_selector

        value, _ = normalize_selector(selector_type, surface_text)
        return value or surface_text.strip()
    return normalize_name(surface_text)


def _carry_piece(correction: TextCorrection, start: int, end: int) -> tuple[int, int]:
    """Carry one of a text's consecutive pieces (page, chunk): text inserted at a boundary joins the earlier one."""
    new_start, _ = correction.map_position(start, bias="left" if start == 0 else "right")
    new_end, _ = correction.map_position(end, bias="right")
    return new_start, new_end


def _carry_prechunked(correction: TextCorrection, spans: list[PrechunkedSpan] | None) -> list[PrechunkedSpan] | None:
    if not spans:
        return spans
    carried = []
    for span in spans:
        start, end = _carry_piece(correction, span.start_offset, span.end_offset)
        carried.append(
            span.model_copy(update={"start_offset": start, "end_offset": end, "content": correction.new[start:end]})
        )
    return carried


def _label(row: MentionTable) -> str:
    return str(row.selector_type or row.entity_type or "mention")


async def correct_text(
    session: "AsyncSession",
    *,
    file_id: str,
    content: str,
    corrected_by: str,
    chunk_store: "ChunkRetrievalRepository",
    rerun: list[EnrichmentType] | None = None,
    embed: EmbedPassages | None = None,
    tokenizer=None,
    dry_run: bool = False,
) -> TextCorrectionSummary:
    """Replace `file_id`'s text (and every same-content copy's) with `content`. See the module docstring.

    `chunk_store` must be bound to `session`; `embed`/`tokenizer` are only needed to re-run text
    embedding. Raises `ValueError` when `rerun` names a step that can't be redone on these files.
    """
    file_repo = PostgresFileRepository(session=session)
    file = await file_repo.get_file_by_id(file_id=file_id)
    copies = await file_repo.find_duplicates(sha256=file.sha256)
    texts = await PostgresExtractedTextRepository(session=session).get_by_file_ids([f.id for f in copies])
    texts = {fid: text for fid, text in texts.items() if text.content != content}
    summary = TextCorrectionSummary(file_count=len(texts), kept_count=0)
    if not texts:
        return summary
    impact = await text_change_impact(session, file_ids=list(texts))
    summary.rerunnable, summary.running = impact.rerunnable, impact.running
    rerun = list(dict.fromkeys(rerun or []))
    if unknown := [step for step in rerun if step not in impact.rerunnable]:
        raise ValueError(f"Can't re-run on these files: {', '.join(unknown)}")
    if EnrichmentType.TEXT_EMBEDDING in rerun and (embed is None or tokenizer is None):
        raise ValueError("Re-running text embedding needs the embedding model")

    corrections: dict[str, TextCorrection] = {}
    rows = (
        (
            await session.execute(
                select(MentionTable).where(
                    MentionTable.mentioned_type == MentionedType.EXTRACTED_TEXT,
                    MentionTable.mentioned_id.in_([text.id for text in texts.values()]),
                    MentionTable.start_offset.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    by_text = {text.id: text for text in texts.values()}
    updates: list[dict] = []
    deletes: list[str] = []
    for row in rows:
        old = by_text[row.mentioned_id].content
        correction = corrections.setdefault(old, TextCorrection(old, content))
        move = correction.remap_span(row.start_offset, row.end_offset)
        if move.fate in (SpanFate.MOVED, SpanFate.RELOCATED):
            summary.kept_count += 1
            updates.append({"id": row.id, "start_offset": move.start, "end_offset": move.end})
        elif move.fate == SpanFate.EDITED:
            surface = content[move.start : move.end]
            value = normalized_value_for(surface_text=surface, selector_type=row.selector_type)
            summary.renamed.append(
                CorrectedMention(
                    mention_id=row.id, label=_label(row), surface_text=row.surface_text, new_surface_text=surface
                )
            )
            patch = {"id": row.id, "start_offset": move.start, "end_offset": move.end, "surface_text": surface}
            if value != row.normalized_value:
                patch |= {"normalized_value": value, "entity_id": None}
            updates.append(patch)
        else:
            deletes.append(row.id)
            summary.lost.append(CorrectedMention(mention_id=row.id, label=_label(row), surface_text=row.surface_text))

    edited = texts.get(file_id) or next(iter(texts.values()))
    correction = corrections.setdefault(edited.content, TextCorrection(edited.content, content))
    summary.corrected_ranges = correction.changed_ranges(edited.corrected_ranges)
    new_texts = {}
    for fid, text in texts.items():
        each = corrections.setdefault(text.content, TextCorrection(text.content, content))
        new_texts[fid] = text.model_copy(
            update={
                "content": content,
                "prechunked": _carry_prechunked(each, text.prechunked),
                "is_content_corrected": True,
                "content_corrected_by": corrected_by,
                "corrected_ranges": each.changed_ranges(text.corrected_ranges),
            }
        )
    if dry_run or impact.running:
        return summary

    for text in new_texts.values():
        await session.execute(
            update(ExtractedTextTable)
            .where(ExtractedTextTable.id == text.id)
            .values(
                content=content,
                prechunked=[span.model_dump(mode="json") for span in text.prechunked] if text.prechunked else None,
                is_content_corrected=True,
                content_corrected_by=corrected_by,
                corrected_ranges=[list(r) for r in text.corrected_ranges],
            )
        )
    if deletes:
        await session.execute(delete(MentionTable).where(MentionTable.id.in_(deletes)))
    for patch in updates:
        mention_id = patch.pop("id")
        patch["context"] = _context(content, patch["start_offset"], patch["end_offset"])
        patch["chunk_id"] = None
        await session.execute(update(MentionTable).where(MentionTable.id == mention_id).values(**patch))

    if EnrichmentType.TEXT_EMBEDDING in rerun:
        summary.chunk_count = await _rebuild_chunks(
            chunk_store, copies=copies, new_texts=new_texts, embed=embed, tokenizer=tokenizer
        )
    else:
        summary.chunk_count = await _carry_chunks(
            session,
            sha256=file.sha256,
            old_content={fid: text.content for fid, text in texts.items()},
            corrections=corrections,
        )
    await _assign_chunks(session, file_ids=list(texts))
    await restage_text_readers(
        session,
        file_ids=list(texts),
        sha256s=[file.sha256],
        steps=[step for step in rerun if step not in REBUILT_IN_PLACE],
    )
    if deletes:
        entity_repo = PostgresEntityRepository(session=session)
        for dataset_id in {f.dataset_id for f in copies if f.id in texts}:
            await entity_repo.delete_empty_provisional(dataset_id)
    await session.commit()
    summary.rerun = rerun
    summary.is_saved = True
    return summary


async def _carry_chunks(
    session: "AsyncSession", *, sha256: str, old_content: dict[str, str], corrections: dict[str, TextCorrection]
) -> int:
    """Move the content's search chunks onto the new text in place: same ids and embeddings, new offsets and text."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text("SELECT id, file_id, start_offset, end_offset FROM chunk WHERE sha256 = :s AND NOT is_summary"),
            {"s": sha256},
        )
    ).all()
    carried = 0
    for row in rows:
        if row.file_id not in old_content:
            continue
        correction = corrections[old_content[row.file_id]]
        start, end = _carry_piece(correction, row.start_offset, row.end_offset)
        await session.execute(
            text(
                "UPDATE chunk SET start_offset = :start, end_offset = :end, text = :text, "
                "text_tsv = CASE WHEN text_tsv IS NULL THEN NULL ELSE to_tsvector('simple', :text) END "
                "WHERE id = :id"
            ),
            {"id": row.id, "start": start, "end": end, "text": correction.new[start:end]},
        )
        carried += 1
    return carried


async def _rebuild_chunks(
    chunk_store: "ChunkRetrievalRepository",
    *,
    copies: list,
    new_texts: dict[str, ExtractedText],
    embed: EmbedPassages,
    tokenizer,
) -> int:
    """Re-split and re-embed the new text once, writing one chunk set per dataset that had chunks."""
    from clir.utils.text_chunk import PlainTextChunker

    embedded = [fid for fid in new_texts if await chunk_store.spans_for_file(fid)]
    if not embedded:
        return 0
    chunker = PlainTextChunker(tokenizer=deepcopy(tokenizer), chunk_size=DEFAULT_CHUNK_SIZE)
    spans = _spans_for(new_texts[embedded[0]], chunker)
    embeddings = await embed([span["content"] for span in spans]) if spans else []
    by_id = {f.id: f for f in copies}
    chunks: list[TextChunk] = []
    for dataset_id in sorted({by_id[fid].dataset_id for fid in embedded}):
        members = [fid for fid in embedded if by_id[fid].dataset_id == dataset_id]
        owner = by_id[members[0]]
        for index, (span, embedding) in enumerate(zip(spans, embeddings, strict=True)):
            chunk = _build_chunk(
                extracted=new_texts[owner.id],
                dataset_id=dataset_id,
                filetype=owner.filetype,
                sha256=owner.sha256,
                span=span,
                chunk_index=index,
                embedding=embedding,
            )
            chunks.append(chunk.model_copy(update={"duplicate_file_ids": members}))
    for fid in embedded:
        await chunk_store.delete_by_file_id(fid)
    await chunk_store.bulk_index(chunks)
    return len(spans)


async def _assign_chunks(session: "AsyncSession", *, file_ids: list[str]) -> None:
    """Point these files' text mentions at the chunk holding their start offset."""
    from sqlalchemy import text

    await session.execute(
        text(
            "UPDATE mention m SET chunk_id = c.id FROM chunk c "
            "WHERE m.file_id = ANY(:files) AND m.start_offset IS NOT NULL AND NOT c.is_summary "
            "AND c.duplicate_file_ids @> to_jsonb(m.file_id) "
            "AND m.start_offset >= c.start_offset AND m.start_offset < c.end_offset"
        ),
        {"files": file_ids},
    )
