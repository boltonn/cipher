"""Entity + relation extraction workflow (ENTITY_EXTRACTION enrichment).

Runs a chosen extractor over a dataset's extracted text and writes, per
text-bearing file:

* unresolved `person` / `organization` / `location` **mention** rows
  (`entity_attribute = name` or `address`) -- the input `resolve-entities`
  turns into entities. Selector-kind labels (phone, email, ...) are left to
  `extract-selectors`, which normalizes and dedupes them properly.
* **`mention_relationship`** rows for every relation the extractor reports
  between two of those spans. The relation is stored against the two mention
  rows, so it is not lost while the spans are still unresolved;
  `resolve-entities` later promotes it into a `RelationshipCandidate` once
  both endpoints carry an entity.

`--extractor` selects the engine, all run in-process:

* `llm`    -- `pyprompt` LLM pack (entities + relations); needs an `LLM__*` config.
* `gliner` -- GLiNER2.5 entities + ontology-typed relations in one joint pass;
             needs `--gliner-model-dir` (a local checkpoint, loaded offline).
* `nerd`   -- supervised token-classification NER (entities only); needs `--nerd-model-dir`.

Re-runnable: a file with a completed ENTITY_EXTRACTION row is skipped until
`reset-entities` clears it (which also drops the mentions and their relations).
"""

import asyncio
from typing import TYPE_CHECKING, Protocol

from loguru import logger
from pyselectors.domains import web_host_containing
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
    PostgresMentionRelationshipRepository,
    PostgresMentionRepository,
)
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas._base.common import ModelDevice
from cipher.schemas.graph.mention import MentionCreate, MentionedType
from cipher.schemas.graph.mention_relationship import MentionRelationshipCreate
from cipher.schemas.graph.ontology import (
    RELATION_LABEL_TO_TYPE,
    EntityType,
    ResolutionPolicy,
    mention_target,
)
from cipher.schemas.graph.spans import EntitySpan, RelationSpan
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_CONTEXT_WINDOW = 80
_PERSISTED_TYPES = {EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION}
_EXTRACTORS = ("llm", "gliner", "nerd")

# Default span-score floor per extractor, used when --threshold is not passed.
# Measured against real production data + gold multilingual corpora: nerd's
# score is well-calibrated only once its span decoding is correct (see
# `nerd.model.NerdModel`'s word-pooled merge) and gains nothing from a floor
# above 0.5 -- precision is already 88-99% there and only recall drops as the
# floor rises. gliner is zero-shot and genuinely under-confident on a lot of
# real spans; 0.65 trades a bit of recall for meaningfully higher precision.
_DEFAULT_THRESHOLD = {"gliner": 0.65, "nerd": 0.5}


# --------------------------------------------------------------------------- #
# Extractor abstraction -- one async `extract(content)` per engine            #
# --------------------------------------------------------------------------- #
class _Extractor(Protocol):
    name: str
    model_label: str | None

    async def extract(self, content: str) -> tuple[list[EntitySpan], list[RelationSpan]]: ...


class _LlmExtractor:
    """`pyprompt` LLM pack -- entities and relations in one call."""

    name = "llm"

    def __init__(self, model: str | None):
        from pyprompt import PromptRunner, Settings

        settings = Settings()
        self._runner = PromptRunner(settings)
        self._model = model
        self.model_label = model or settings.llm.model

    async def extract(self, content: str) -> tuple[list[EntitySpan], list[RelationSpan]]:
        result = await self._runner.extract_entities(content, model=self._model)
        return list(result.entities), list(result.relations)


class _GlinerExtractor:
    """GLiNER2.5 entities, plus relations from a joint pass unless disabled."""

    name = "gliner"

    def __init__(self, *, gliner_model_dir: str, relations: bool, threshold: float, device: ModelDevice):
        from pygliner.model import GlinerModel

        self._model = GlinerModel(gliner_model_dir, device=device)
        self._relations = relations
        self._threshold = threshold
        self.model_label = gliner_model_dir.rstrip("/").split("/")[-1]

    async def extract(self, content: str) -> tuple[list[EntitySpan], list[RelationSpan]]:
        if not self._relations:
            return await asyncio.to_thread(self._model.infer, content, None, self._threshold), []
        return await asyncio.to_thread(self._model.extract, content, None, None, self._threshold)


class _NerdExtractor:
    """Supervised token-classification NER -- entities only."""

    name = "nerd"

    def __init__(self, *, nerd_model_dir: str, threshold: float, device: ModelDevice):
        from nerd.model import NerdModel

        self._ner = NerdModel(nerd_model_dir, device=device)
        self._threshold = threshold
        self.model_label = nerd_model_dir.rstrip("/").split("/")[-1]

    async def extract(self, content: str) -> tuple[list[EntitySpan], list[RelationSpan]]:
        entities = await asyncio.to_thread(self._ner.infer, content, self._threshold)
        return entities, []

    async def extract_batch(self, contents: list[str]) -> list[tuple[list[EntitySpan], list[RelationSpan]]]:
        """One packed pass over many files -- the GPU throughput path."""
        results = await asyncio.to_thread(self._ner.infer_batch, contents, self._threshold)
        return [(entities, []) for entities in results]


def _build_extractor(
    extractor: str,
    *,
    model: str | None,
    gliner_model_dir: str | None,
    nerd_model_dir: str | None,
    threshold: float | None,
    relations: bool = True,
    device: ModelDevice = ModelDevice.CPU,
) -> _Extractor:
    if extractor == "llm":
        return _LlmExtractor(model)
    resolved_threshold = threshold if threshold is not None else _DEFAULT_THRESHOLD.get(extractor, 0.5)
    if extractor == "gliner":
        if not gliner_model_dir:
            raise ValueError("extract-entities --extractor gliner needs --gliner-model-dir")
        return _GlinerExtractor(
            gliner_model_dir=gliner_model_dir,
            relations=relations,
            threshold=resolved_threshold,
            device=device,
        )
    if extractor == "nerd":
        if not nerd_model_dir:
            raise ValueError("extract-entities --extractor nerd needs --nerd-model-dir")
        return _NerdExtractor(nerd_model_dir=nerd_model_dir, threshold=resolved_threshold, device=device)
    raise ValueError(f"Unknown --extractor '{extractor}' (choose from {_EXTRACTORS})")


# --------------------------------------------------------------------------- #
# Span -> row mapping                                                         #
# --------------------------------------------------------------------------- #
def _context(content: str, start: int, end: int) -> str:
    """A windowed snippet around a span (or a span pair), for the Review queue."""
    lo = max(0, start - _CONTEXT_WINDOW)
    hi = min(len(content), end + _CONTEXT_WINDOW)
    return content[lo:hi].replace("\n", " ").strip()


def _to_mention(
    span: EntitySpan,
    *,
    dataset_id: str,
    file_id: str,
    extracted_id: str,
    content: str,
    extractor: str,
    model: str | None,
) -> MentionCreate | None:
    """Map one entity span to an unresolved name/address mention, or None to skip it."""
    target = mention_target(span.label)
    if target is None or target.entity_type not in _PERSISTED_TYPES:
        return None
    if target.selector_type is not None or target.resolution == ResolutionPolicy.BY_VALUE:
        return None

    surface = span.surface_text.strip()
    if not surface:
        return None
    # `Udemy.com`, or `Towards` cut from `towardsdatascience.com`: a website is a `domain`
    # selector (the pattern pass records it), never a person/organization name
    if target.attribute == "name" and web_host_containing(content, span.start_offset, span.end_offset):
        return None

    return MentionCreate(
        dataset_id=dataset_id,
        mentioned_type=MentionedType.EXTRACTED_TEXT,
        mentioned_id=extracted_id,
        file_id=file_id,
        surface_text=surface,
        entity_type=target.entity_type,
        entity_attribute=target.attribute,
        normalized_value=normalize_name(surface) if target.attribute == "name" else surface,
        start_offset=span.start_offset,
        end_offset=span.end_offset,
        context=_context(content, span.start_offset, span.end_offset),
        extractor=extractor,
        extraction_model=model,
        extraction_confidence=span.score,
    )


class MentionRowRef:
    """Just the mention fields the relation mapper needs."""

    __slots__ = ("id", "start", "end")

    def __init__(self, id: str, start: int, end: int):
        self.id = id
        self.start = start
        self.end = end


def _relations_for_file(
    relations: list[RelationSpan],
    mentions_by_start: dict[int, MentionRowRef],
    *,
    dataset_id: str,
    file_id: str,
    content: str,
    extractor: str,
    model: str | None,
) -> list[MentionRelationshipCreate]:
    """Turn relation spans into `mention_relationship` rows between persisted mentions."""
    out: list[MentionRelationshipCreate] = []
    seen: set[tuple[str, str, str]] = set()
    for rel in relations:
        rel_type = RELATION_LABEL_TO_TYPE.get(rel.label.strip().lower())
        if rel_type is None:
            continue
        head = mentions_by_start.get(rel.head_start)
        tail = mentions_by_start.get(rel.tail_start)
        if head is None or tail is None or head.id == tail.id:
            continue
        key = (head.id, tail.id, rel_type.value)
        if key in seen:
            continue
        seen.add(key)
        lo = min(head.start, tail.start)
        hi = max(head.end, tail.end)
        out.append(
            MentionRelationshipCreate(
                dataset_id=dataset_id,
                src_mention_id=head.id,
                dst_mention_id=tail.id,
                relationship_type=rel_type,
                confidence=rel.score,
                file_id=file_id,
                context=_context(content, lo, hi),
                extractor=extractor,
                extraction_model=model,
            )
        )
    return out


async def persist_file_entities(
    *,
    spans: list[EntitySpan],
    relations: list[RelationSpan],
    dataset_id: str,
    file_id: str,
    extracted_id: str,
    content: str,
    extractor: str,
    model: str | None,
    mention_repo: PostgresMentionRepository,
    relation_repo: PostgresMentionRelationshipRepository,
    persist_relations: bool = True,
) -> tuple[int, int]:
    """Write one file's entity spans + relations as `mention` / `mention_relationship` rows.

    Returns `(mentions_written, relations_written)`. Shared by
    `extract_entities_workflow` and the combined `extract_llm_workflow`.
    """
    mentions = [
        m
        for span in spans
        if (
            m := _to_mention(
                span,
                dataset_id=dataset_id,
                file_id=file_id,
                extracted_id=extracted_id,
                content=content,
                extractor=extractor,
                model=model,
            )
        )
        is not None
    ]
    saved = await mention_repo.add_mentions_returning(mentions)

    relation_count = 0
    if persist_relations and relations and saved:
        by_start = {
            m.start_offset: MentionRowRef(m.id, m.start_offset, m.end_offset)
            for m in saved
            if m.start_offset is not None and m.end_offset is not None
        }
        rel_rows = _relations_for_file(
            relations,
            by_start,
            dataset_id=dataset_id,
            file_id=file_id,
            content=content,
            extractor=extractor,
            model=model,
        )
        relation_count = await relation_repo.add_batch(rel_rows)
    return len(saved), relation_count


async def queue_entity_extraction_enrichments(session: "AsyncSession", dataset_id: str) -> int:
    """Queue ENTITY_EXTRACTION enrichments for every file in the dataset without one."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = await enrichment_repo.queue_enrichments_by_filter(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.ENTITY_EXTRACTION,
    )
    await session.commit()
    return count


async def extract_entities_workflow(
    session: "AsyncSession",
    dataset_id: str,
    *,
    extractor: str = "llm",
    batch_size: int = 25,
    model: str | None = None,
    gliner_model_dir: str | None = None,
    nerd_model_dir: str | None = None,
    threshold: float | None = None,
    persist_relations: bool = True,
    device: ModelDevice = ModelDevice.CPU,
) -> int:
    """Run NER + relation extraction over a dataset's text. Returns files processed."""
    engine = _build_extractor(
        extractor,
        model=model,
        gliner_model_dir=gliner_model_dir,
        nerd_model_dir=nerd_model_dir,
        threshold=threshold,
        relations=persist_relations,
        device=device,
    )

    await queue_entity_extraction_enrichments(session=session, dataset_id=dataset_id)

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    mention_repo = PostgresMentionRepository(session=session)
    relation_repo = PostgresMentionRelationshipRepository(session=session)

    total = await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.ENTITY_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
    )
    count = failed_count = mention_count = relation_count = 0

    with tqdm(total=total, desc=f"Extracting entities ({engine.name})", unit=" file") as pbar:
        while True:
            batch = await enrichment_repo.get_pending_batch(
                enrichment_type=EnrichmentType.ENTITY_EXTRACTION,
                enrichable_type=EnrichableType.FILE,
                batch_size=batch_size,
                dataset_id=dataset_id,
            )
            if not batch:
                break

            await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            texts = await extracted_text_repo.get_by_file_ids([item.resource["id"] for item in batch])
            precomputed: dict[str, tuple[list[EntitySpan], list[RelationSpan]]] = {}
            if isinstance(engine, _NerdExtractor):
                todo = {fid: t.content for fid, t in texts.items() if t.content and t.content.strip()}
                try:
                    precomputed = dict(zip(todo, await engine.extract_batch(list(todo.values())), strict=True))
                except Exception as e:
                    logger.warning(f"Batched nerd pass failed, falling back to per-file: {e}")

            completed, failed = [], {}
            for item in batch:
                file_id = item.resource["id"]
                try:
                    extracted = texts.get(file_id)
                    content = (extracted.content or "") if extracted is not None else ""
                    if not content.strip():
                        completed.append(item.enrichment.id)
                        continue

                    spans, relations = precomputed.get(file_id) or await engine.extract(content)
                    written_mentions, written_relations = await persist_file_entities(
                        spans=spans,
                        relations=relations,
                        dataset_id=dataset_id,
                        file_id=file_id,
                        extracted_id=extracted.id,
                        content=content,
                        extractor=engine.name,
                        model=engine.model_label,
                        mention_repo=mention_repo,
                        relation_repo=relation_repo,
                        persist_relations=persist_relations,
                    )
                    mention_count += written_mentions
                    relation_count += written_relations

                    completed.append(item.enrichment.id)
                except Exception as e:
                    logger.error(f"Entity extraction failed for file {file_id}: {e}")
                    await session.rollback()
                    failed[item.enrichment.id] = e

            if completed:
                await enrichment_repo.mark_completed_batch(completed)
            await enrichment_repo.mark_failed(failed)
            await session.commit()

            count += len(completed)
            failed_count += len(failed)
            pbar.set_postfix(failed=failed_count, mentions=mention_count, relations=relation_count)
            pbar.update(len(completed) + len(failed))

    logger.success(
        f"Extracted {mention_count} name/address mentions and {relation_count} mention relations "
        f"from {count} files ({failed_count} failed)"
    )
    return count


async def get_entity_extraction_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Enrichment stats for entity extraction."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.ENTITY_EXTRACTION,
    )
