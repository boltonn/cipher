"""`POST /search/overview`: every lane at once, plus the layout the rules router picked.

See docs/global-search.md §3–5.
"""

from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas.content.image import ImageSimilarityResult
from cipher.schemas.content.results import FileSearchResult, ResultShape
from cipher.schemas.graph.entity import EntitySearchResult
from cipher.schemas.graph.event import Event
from cipher.schemas.graph.location import Location
from cipher.schemas.graph.ontology import EntityType
from cipher.schemas.identity.face import FacePublic
from cipher.schemas.ingestion.file import File
from cipher.schemas.interaction.search_record import SearchRecord, SearchRequest


class LaneName(StrEnum):
    TEXT = "text"
    ENTITIES = "entities"
    IMAGES = "images"
    FILES = "files"
    EVENTS = "events"
    PLACES = "places"
    FACES = "faces"


class LaneStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    ERROR = "error"


class QueryKind(StrEnum):
    """What the rules router took the query to be."""

    SELECTOR = "selector"
    NAME = "name"
    IMAGE = "image"
    QUESTION = "question"
    TOPIC = "topic"


class Lane[T](BaseModel):
    """One lane's preview: its top items, a capped total, and (text only) the result shape."""

    status: LaneStatus = LaneStatus.OK
    items: list[T] = Field(default_factory=list)
    total: int = 0
    total_is_exact: bool = Field(default=True, description="False when `total` is a floor (capped)")
    shape: ResultShape | None = None
    took_ms: int = 0


class OverviewLayout(BaseModel):
    """How to arrange the page, from rules over the query and the lanes' own results (no LLM)."""

    query_kind: QueryKind
    hero: LaneName | None = Field(default=None, description="Lane to feature at the top, if any")
    lane_order: list[LaneName] = Field(description="Non-empty lanes, strongest first")
    is_question: bool = False
    image_query: str | None = Field(default=None, description="The CLIP query when `photos of …` was stripped")


class OverviewResponse(BaseModel):
    """The whole results page for one search."""

    search_id: str
    request: SearchRequest = Field(
        description="The question this page answers -- fills the search box and filter chips"
    )
    trail: list[SearchRecord] = Field(
        default_factory=list, description="The searches this one was narrowed from, oldest first, ending with itself"
    )
    layout: OverviewLayout
    text: Lane[FileSearchResult]
    entities: Lane[EntitySearchResult]
    images: Lane[ImageSimilarityResult]
    files: Lane[File]
    events: Lane[Event]
    places: Lane[Location]
    faces: Lane[FacePublic] = Field(description="Faces of the people the query names, best quality first")
    took_ms: int


class AssistCitation(BaseModel):
    """A passage the AI answer was grounded in."""

    number: int = Field(description="The `[n]` marker the answer uses for it")
    file_id: str
    chunk_id: str
    title: str


class SearchSuggestion(BaseModel):
    """A narrower search the AI read out of the wording -- offered, never applied automatically."""

    label: str = Field(description="What it would narrow to, e.g. `email · March 2026 · Megan Flick`")
    request: SearchRequest


class NameOption(BaseModel):
    """One thing a typed name might mean: a person, an auto-created spelling, or an email address."""

    entity_ids: list[str] = Field(description="Every entity under this spelling (stubs that differ only in case)")
    display_name: str
    entity_type: EntityType
    is_provisional: bool = False
    detail: str | None = Field(default=None, description="e.g. `986 emails · linked to Nick Bolton`")
    is_suggested: bool = Field(default=False, description="Ticked by default: very likely the same person")


class NameChoice(BaseModel):
    """A name from the search text and the entities it could mean -- the user ticks which to search for."""

    name: str = Field(description="As typed")
    options: list[NameOption]


class SearchAssist(BaseModel):
    """The AI part of a results page, from the backend's default LLM; cached on the search record."""

    answer: str | None = Field(default=None, description="Short answer from the top passages; only for questions")
    citations: list[AssistCitation] = Field(default_factory=list)
    suggestion: SearchSuggestion | None = None
    is_visual: bool = Field(default=False, description="The model reads the search as about what's in photos")
    name_choices: list[NameChoice] = Field(
        default_factory=list, description="Names in the search that could mean more than one entity"
    )
    model: str


class DatasetBrief(BaseModel):
    """AI summary of a dataset profile plus starting searches; saved until regenerated on request."""

    summary: str
    suggested_searches: list[str] = Field(default_factory=list)
    model: str
    date_generated: datetime | None = Field(default=None)
    is_outdated: bool = Field(
        default=False, description="The profile was recomputed after this summary was written (not stored)"
    )
