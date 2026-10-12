"""Global search overview: every lane in parallel under a time budget, laid out by rules (no LLM).

See docs/global-search.md §4–5.
"""

import asyncio
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
from loguru import logger
from pyselectors.extract import extract_selectors

from cipher.api.deps.postgres import get_session
from cipher.datastores.base.retrieval import ChunkRetrievalRepository
from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository
from cipher.datastores.postgres.repositories.face import PostgresFaceRepository
from cipher.datastores.postgres.repositories.global_search import PostgresGlobalSearchRepository
from cipher.datastores.postgres.repositories.image import PostgresImageRepository
from cipher.names import Level, compare_names
from cipher.schemas.content.image import ImageSimilarityResult, ImageSimilaritySearchRequest
from cipher.schemas.content.results import PaginatedFileSearchResponse
from cipher.schemas.content.search import ChunkFilters, RetrievalMode, RetrievalQuery
from cipher.schemas.graph.entity import EntitySearchResult
from cipher.schemas.graph.ontology import EntityType
from cipher.schemas.identity.face import BaseFaceSearchParameters, FaceSortField
from cipher.schemas.interaction.global_search import (
    Lane,
    LaneName,
    LaneStatus,
    OverviewLayout,
    QueryKind,
)
from cipher.schemas.interaction.search_record import SearchRequest

TEXT_PREVIEW = 5
ENTITY_PREVIEW = 5
IMAGE_PREVIEW = 8
FACE_PREVIEW = 12
IMAGE_CANDIDATES = 24
IMAGE_HERO_MIN = 6  # of IMAGE_CANDIDATES that must pass the zero-shot test for images to lead
NAME_MATCH_HERO = 0.6
MIN_NAME_QUERY = 3  # trigram indexes need 3 characters

_QUESTION_WORDS = ("who", "what", "when", "where", "why", "how", "which", "did", "does", "is", "are", "was", "can")
_IMAGE_PREFIX = re.compile(r"^(?:photos?|pictures?|pics?|images?)\s+(?:of|from|with|showing)\s+(?P<rest>.+)$", re.I)
# CLIP's absolute text->image similarity doesn't track relevance ("invoice" outscores "photos of the
# beach"), so images only lead for an image query and otherwise sit last as a "visually related" strip.
# The image lane only keeps images where the query beats these generic captions (zero-shot), so
# its size -- not the raw similarity -- says whether the query is something you can see.
_IMAGE_BACKGROUND = (
    "a photo",
    "a screenshot",
    "a document with text",
    "a logo or graphic",
    "a photo of a person",
    "a photo of a group of people",
    "a photo of a room",
    "a photo outdoors",
    "a chart or table",
)
_CLIP_LOGIT_SCALE = 100.0
_DEFAULT_ORDER = (
    LaneName.TEXT,
    LaneName.ENTITIES,
    LaneName.FACES,
    LaneName.IMAGES,
    LaneName.EVENTS,
    LaneName.PLACES,
    LaneName.FILES,
)
_ORDER_BY_KIND = {
    QueryKind.SELECTOR: (
        LaneName.ENTITIES,
        LaneName.TEXT,
        LaneName.FILES,
        LaneName.EVENTS,
        LaneName.PLACES,
        LaneName.FACES,
        LaneName.IMAGES,
    ),
    QueryKind.NAME: (
        LaneName.ENTITIES,
        LaneName.FACES,
        LaneName.TEXT,
        LaneName.EVENTS,
        LaneName.PLACES,
        LaneName.FILES,
        LaneName.IMAGES,
    ),
    QueryKind.IMAGE: (
        LaneName.IMAGES,
        LaneName.TEXT,
        LaneName.FACES,
        LaneName.ENTITIES,
        LaneName.EVENTS,
        LaneName.PLACES,
        LaneName.FILES,
    ),
}


@dataclass(frozen=True)
class QueryPlan:
    """What the rules read from the query string alone, before any lane runs."""

    kind: QueryKind
    is_question: bool
    entity_query: str
    image_query: str
    stripped_image_prefix: bool


def plan_query(query: str) -> QueryPlan:
    """Classify the query: a selector (email/phone/domain…), an image request, a question, or a topic."""
    query = " ".join(query.split())
    lowered = query.lower()
    is_question = query.endswith("?") or lowered.split(" ", 1)[0] in _QUESTION_WORDS
    selectors = extract_selectors(query) if query else []
    covered = sum(span.end_offset - span.start_offset for span in selectors)
    if selectors and covered >= 0.8 * len(query.replace(" ", "")):
        return QueryPlan(QueryKind.SELECTOR, False, selectors[0].normalized_value, query, False)
    if match := _IMAGE_PREFIX.match(query):
        rest = match.group("rest")
        return QueryPlan(QueryKind.IMAGE, False, rest, rest, True)
    kind = QueryKind.QUESTION if is_question else QueryKind.TOPIC
    return QueryPlan(kind, is_question, query, query, False)


_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_MONTH_DATE = re.compile(
    r"\b(?:(?P<prep>in|during|from|on|of|since|until|before|after)\s+)?(?P<month>"
    + "|".join(sorted(_MONTHS, key=len, reverse=True))
    + r")\.?"
    r"(?:\s+(?P<year>(?:19|20)\d{2}))?\b",
    re.I,
)
_YEAR_DATE = re.compile(r"\b(?:in|during|from|of)?\s*(?P<year>(?:19|20)\d{2})\b", re.I)
_FILETYPE_WORDS = {
    "email": ("email", "emails", "e-mail", "e-mails", "mail", "emailed", "mailed"),
    "document": ("document", "documents", "doc", "docs", "pdf", "pdfs"),
}
_FILLER_WORDS = set(_QUESTION_WORDS) | {
    "do", "were", "me", "my", "i", "you", "about", "the", "a", "an", "in", "on", "of", "from", "to", "for",
    "with", "any", "all", "show", "find", "get", "sent", "received", "by", "and", "or", "that", "this", "us", "we",
    "has", "have", "had", "been",
}  # fmt: skip


@dataclass(frozen=True)
class QueryFilters:
    """Dates, file types and the leftover subject words read out of a query by rules (no model)."""

    topic: str
    date_from: date | None
    date_to: date | None
    filetype_groups: tuple[str, ...]


def read_query_filters(query: str, *, today: date, names: list[str] = ()) -> QueryFilters:
    """Read a month / year and file-type words out of `query`; what's left (minus `names`) is the topic.

    A month without a year is its most recent occurrence on or before `today`.
    """
    text = " ".join(query.split())
    date_from = date_to = None
    # A bare month counts only after a preposition or with a year ("may the force" is not May).
    month_matches = [m for m in _MONTH_DATE.finditer(text) if m.group("prep") or m.group("year")]
    if match := (month_matches[0] if month_matches else None):
        month = _MONTHS[match.group("month").lower()]
        year = int(match.group("year")) if match.group("year") else today.year - (month > today.month)
        date_from = date(year, month, 1)
        date_to = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
        text = text[: match.start()] + " " + text[match.end() :]
    elif match := _YEAR_DATE.search(text):
        year = int(match.group("year"))
        date_from, date_to = date(year, 1, 1), date(year, 12, 31)
        text = text[: match.start()] + " " + text[match.end() :]
    for name in names:
        text = re.sub(re.escape(name), " ", text, flags=re.I)
    words = [word.strip("?.,!:;\"'") for word in text.split()]
    groups = tuple(group for group, terms in _FILETYPE_WORDS.items() if any(w.lower() in terms for w in words))
    filetype_terms = {term for terms in _FILETYPE_WORDS.values() for term in terms}
    topic = [w for w in words if w and w.lower() not in _FILLER_WORDS and w.lower() not in filetype_terms]
    return QueryFilters(topic=" ".join(topic), date_from=date_from, date_to=date_to, filetype_groups=groups)


def names_person(query: str, entity: EntitySearchResult) -> bool:
    """The query is this person's name, structurally (nicknames and initials count, not just trigrams)."""
    return entity.entity_type == EntityType.PERSON and compare_names(query, entity.display_name).level >= Level.STRONG


def arrange(plan: QueryPlan, lanes: dict[LaneName, Lane]) -> OverviewLayout:
    """Order the lanes and pick a hero from the plan plus the lanes' own results.

    A topic becomes a name when it names a person, else an image query when enough images pass the
    zero-shot test, else a name when any entity matches closely (an org called "Cats" doesn't beat
    23 photos of cats).
    """
    kind = plan.kind
    entities = lanes[LaneName.ENTITIES].items
    if kind == QueryKind.TOPIC:
        if lanes[LaneName.FACES].items or any(names_person(plan.entity_query, entity) for entity in entities):
            kind = QueryKind.NAME
        elif lanes[LaneName.IMAGES].total >= IMAGE_HERO_MIN:
            kind = QueryKind.IMAGE
        elif any(entity.score >= NAME_MATCH_HERO for entity in entities):
            kind = QueryKind.NAME
    order = _ORDER_BY_KIND.get(kind, _DEFAULT_ORDER)
    visible = [name for name in order if lanes[name].status != LaneStatus.EMPTY]
    hero = {
        QueryKind.SELECTOR: LaneName.ENTITIES,
        QueryKind.NAME: LaneName.ENTITIES,
        QueryKind.IMAGE: LaneName.IMAGES,
    }.get(kind)
    return OverviewLayout(
        query_kind=kind,
        hero=hero if hero in visible else None,
        lane_order=visible,
        is_question=plan.is_question,
        image_query=plan.image_query if plan.stripped_image_prefix else None,
    )


def visible_image_ids(
    *, query_vector: list[float], background: list[list[float]], embeddings: dict[str, list[float]], ids: list[str]
) -> list[str]:
    """The ids (in order) whose CLIP softmax prefers the query over every generic caption combined."""
    kept = [image_id for image_id in ids if image_id in embeddings]
    if not kept:
        return []
    images = np.asarray([embeddings[image_id] for image_id in kept], dtype=np.float32)
    captions = np.asarray([query_vector, *background], dtype=np.float32)
    logits = _CLIP_LOGIT_SCALE * images @ captions.T
    logits -= logits.max(axis=1, keepdims=True)
    probabilities = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    return [image_id for image_id, p in zip(kept, probabilities[:, 0], strict=True) if p > 0.5]


class _EmbeddingCache:
    """Query embeddings by (model, text): Back, re-runs and added filters don't re-embed."""

    def __init__(self, size: int = 512):
        self._items: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        self._size = size

    async def get(
        self, model: str, text: str, embed: Callable[[], Awaitable[list[float] | None]]
    ) -> list[float] | None:
        key = (model, text)
        if key in self._items:
            self._items.move_to_end(key)
            return self._items[key]
        vector = await embed()
        if vector is not None:
            self._items[key] = vector
            if len(self._items) > self._size:
                self._items.popitem(last=False)
        return vector


_embeddings = _EmbeddingCache()


async def _timed[T](coro: Awaitable[Lane[T]], budget_s: float, name: LaneName) -> Lane[T]:
    started = time.perf_counter()
    try:
        lane = await asyncio.wait_for(coro, timeout=budget_s)
    except TimeoutError:
        lane = Lane(status=LaneStatus.TIMEOUT)
    except Exception:  # noqa: BLE001 -- one lane failing must not fail the page
        logger.exception(f"overview lane {name} failed")
        lane = Lane(status=LaneStatus.ERROR)
    if lane.status == LaneStatus.OK and not lane.items:
        lane.status = LaneStatus.EMPTY
    lane.took_ms = round((time.perf_counter() - started) * 1000)
    return lane


def _empty() -> Lane:
    return Lane(status=LaneStatus.EMPTY)


async def run_text_search(
    *,
    request: SearchRequest,
    dataset_ids: list[str] | None,
    chunks: ChunkRetrievalRepository,
    text_model,
    limit: int,
) -> PaginatedFileSearchResponse | None:
    """The text lane's search (hybrid, or a filtered browse with no query); None when it can't apply."""
    filters = request.filters
    query = " ".join(request.query.split())
    text_groups = [group for group in filters.filetype_groups if group in ("document", "email")]
    if filters.filetype_groups and not text_groups:
        return None
    if not query and not (
        filters.entity_ids or filters.entity_groups or filters.date_from or filters.date_to or text_groups
    ):
        return None
    text_vec = (
        await _embeddings.get("text", query, lambda: text_model.infer(text=query, task="retrieval"))
        if query and not filters.exact_match
        else None
    )
    return await chunks.search(
        RetrievalQuery(
            mode=RetrievalMode.HYBRID if text_vec is not None else RetrievalMode.KEYWORD,
            text=query or None,
            exact_match=filters.exact_match,
            embedding=text_vec,
            limit=limit,
            include_shape=True,
            filters=ChunkFilters(
                dataset_ids=dataset_ids,
                entity_ids=filters.entity_ids or None,
                entity_groups=filters.entity_groups or None,
                filetype_group=text_groups[0] if len(text_groups) == 1 else None,
                date_from=filters.date_from,
                date_to=filters.date_to,
            ),
        )
    )


async def run_overview(
    *,
    request: SearchRequest,
    dataset_ids: list[str] | None,
    chunks: ChunkRetrievalRepository,
    images: PostgresImageRepository,
    text_model,
    image_model,
    budget_ms: int,
) -> tuple[OverviewLayout, dict[LaneName, Lane]]:
    """Run every lane concurrently (three sessions: text, images, names) and lay out the page.

    Each lane embeds its own query, so name lookups never wait on model inference, and the
    budget covers inference too.

    `dataset_ids` is the caller's access-scoped dataset filter (None = all, admin). Content lanes
    (text, images, files) respect it; entities, events and places are the shared graph.
    """
    plan = plan_query(request.query)
    filters = request.filters
    query = " ".join(request.query.split())
    budget_s = budget_ms / 1000
    wants = set(filters.filetype_groups)

    async def text_lane() -> Lane:
        result = await run_text_search(
            request=request, dataset_ids=dataset_ids, chunks=chunks, text_model=text_model, limit=TEXT_PREVIEW
        )
        if result is None:
            return _empty()
        return Lane(items=result.data, total=result.total, total_is_exact=result.total_is_exact, shape=result.shape)

    async def image_lane() -> Lane:
        if not query or (wants and "image" not in wants):
            return _empty()
        date_from, date_to = filters.datetime_range()
        items = await images_matching_text(
            text=plan.image_query,
            images=images,
            image_model=image_model,
            dataset_ids=dataset_ids,
            date_from=date_from,
            date_to=date_to,
        )
        if items is None:
            return _empty()
        return Lane(items=items[:IMAGE_PREVIEW], total=len(items), total_is_exact=len(items) < IMAGE_CANDIDATES)

    async def name_lanes() -> dict[LaneName, Lane]:
        async with get_session() as session:
            lookups = PostgresGlobalSearchRepository(session=session)
            entity_query = plan.entity_query
            out: dict[LaneName, Lane] = {}
            if len(query) >= MIN_NAME_QUERY:
                out[LaneName.FILES] = await _timed(
                    _files(lookups, query, dataset_ids, filters.filetype_groups), budget_s, LaneName.FILES
                )
                out[LaneName.EVENTS] = await _timed(_events(lookups, query, filters), budget_s, LaneName.EVENTS)
                out[LaneName.PLACES] = await _timed(_places(lookups, query), budget_s, LaneName.PLACES)
            if len(entity_query) >= MIN_NAME_QUERY:
                out[LaneName.ENTITIES] = entities = await _timed(
                    _entities(PostgresEntityRepository(session=session), entity_query), budget_s, LaneName.ENTITIES
                )
                if plan.kind != QueryKind.SELECTOR and (not wants or "image" in wants):
                    out[LaneName.FACES] = await _timed(
                        _faces(PostgresFaceRepository(session=session), entity_query, entities.items, dataset_ids),
                        budget_s,
                        LaneName.FACES,
                    )
            return out

    text, image, names = await asyncio.gather(
        _timed(text_lane(), budget_s, LaneName.TEXT),
        _timed(image_lane(), budget_s, LaneName.IMAGES),
        name_lanes(),
    )
    lanes = {name: names.get(name, _empty()) for name in LaneName} | {LaneName.TEXT: text, LaneName.IMAGES: image}
    return arrange(plan, lanes), lanes


async def images_matching_text(
    *,
    text: str,
    images: PostgresImageRepository,
    image_model,
    dataset_ids: list[str] | None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    tags: list[str] | None = None,
) -> list[ImageSimilarityResult] | None:
    """Images that look like `text` (CLIP), nearest first; None when the image model is unavailable.

    The nearest `IMAGE_CANDIDATES` are kept only if CLIP prefers `text` over every generic caption
    combined, so a query with no real match comes back empty instead of returning the closest noise.
    """
    image_vec, *background = await asyncio.gather(
        *(
            _embeddings.get("image", caption, lambda caption=caption: image_model.infer_text(text=caption))
            for caption in (text, *_IMAGE_BACKGROUND)
        )
    )
    if image_vec is None or any(vector is None for vector in background):
        return None
    result = await images.search_similar_images(
        ImageSimilaritySearchRequest(
            embedding=image_vec,
            datasets=dataset_ids,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
            limit=IMAGE_CANDIDATES,
        )
    )
    ids = [image.id for image in result.data]
    visible = set(
        visible_image_ids(
            query_vector=image_vec, background=background, embeddings=await images.get_embeddings(ids), ids=ids
        )
    )
    return [image for image in result.data if image.id in visible]


async def _entities(repo: PostgresEntityRepository, query: str) -> Lane:
    items = await repo.search_by_name(dataset_id=None, query=query, limit=ENTITY_PREVIEW)
    return Lane(items=items, total=len(items), total_is_exact=len(items) < ENTITY_PREVIEW)


async def _faces(
    repo: PostgresFaceRepository, query: str, entities: list[EntitySearchResult], dataset_ids: list[str] | None
) -> Lane:
    """Faces of the people the query names (assigned or pending a match), best quality first."""
    person_ids = [
        entity.id
        for entity in entities
        if entity.entity_type == EntityType.PERSON and compare_names(query, entity.display_name).level >= Level.STRONG
    ]
    if not person_ids:
        return _empty()
    result = await repo.search_faces(
        BaseFaceSearchParameters(
            person_ids=person_ids,
            datasets=dataset_ids,
            sort_by=FaceSortField.QUALITY,
            limit=FACE_PREVIEW,
        )
    )
    return Lane(items=result.data, total=result.total)


async def _files(repo: PostgresGlobalSearchRepository, query: str, dataset_ids, filetype_groups) -> Lane:
    items, total, exact = await repo.files_by_name(
        query=query, dataset_ids=dataset_ids, filetype_groups=filetype_groups
    )
    return Lane(items=items, total=total, total_is_exact=exact)


async def _events(repo: PostgresGlobalSearchRepository, query: str, filters) -> Lane:
    date_from, date_to = filters.datetime_range()
    items, total, exact = await repo.events_by_title(query=query, date_from=date_from, date_to=date_to)
    return Lane(items=items, total=total, total_is_exact=exact)


async def _places(repo: PostgresGlobalSearchRepository, query: str) -> Lane:
    items, total, exact = await repo.places_by_name(query=query)
    return Lane(items=items, total=total, total_is_exact=exact)
