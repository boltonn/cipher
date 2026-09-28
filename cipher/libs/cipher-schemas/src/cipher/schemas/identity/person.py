from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, computed_field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PageParams, PaginatedResponse, Sex
from cipher.schemas.identity.face import FaceEmbedding


class PersonSource(StrEnum):
    """How a person record came to exist."""

    MANUAL = "manual"
    FACE_CLUSTERING = "face_clustering"


class PersonSortField(StrEnum):
    NAME = "name"
    DATE_CREATED = "date_created"
    DATE_UPDATED = "date_updated"


class PersonBase(BaseModel):
    """Base person schema.

    A Person represents a real-world individual of interest to an
    investigation. It is a standalone identity concept, independent of
    system users/analysts, and is intended to be referenced from many
    kinds of evidence (faces today; contacts, devices, message senders,
    etc. in the future) rather than owned by any single one.
    """

    name: str | None = Field(default=None, max_length=255, description="Display name")
    aliases: list[str] = Field(default_factory=list, description="Known alternate names")
    notes: str | None = Field(default=None, description="Analyst notes")
    tags: list[str] = Field(default_factory=list, description="Free-form tags")
    date_of_birth: datetime | None = Field(default=None, description="Date of birth, if known")
    sex: Sex | None = Field(default=None, description="Sex of the person, if known")
    is_verified: bool = Field(
        default=False,
        description="Whether an analyst has confirmed this as a distinct identity",
    )
    source: PersonSource = Field(default=PersonSource.MANUAL, description="How this person record was created")


class PersonCreate(PersonBase):
    """Person creation schema."""

    @computed_field
    @property
    def date_created(self) -> datetime:
        """Automatically set the creation date to now."""
        return datetime.now(UTC)

    @computed_field
    @property
    def date_updated(self) -> datetime:
        """Automatically set the last updated date to now."""
        return datetime.now(UTC)


class PersonUpdate(BaseModel):
    """Person update schema."""

    name: str | None = Field(default=None)
    aliases: list[str] | None = Field(default=None)
    notes: str | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    date_of_birth: datetime | None = Field(default=None)
    sex: Sex | None = Field(default=None)
    is_verified: bool | None = Field(default=None)

    @computed_field
    @property
    def date_updated(self) -> datetime:
        """Automatically set the last updated date to now."""
        return datetime.now(UTC)


class PersonMerge(BaseModel):
    """Fold one person record into another.

    Everything attached to ``source_id`` -- faces, pending face matches,
    event participations, comments, name mentions, and relationship edges --
    is repointed onto the person the request is addressed to, then the source
    record (and its entity bridge node) is deleted. Moved faces lose their
    representative/primary flags, since exemplar curation is specific to the
    record it was done on; re-pick them on the survivor.
    """

    source_id: str = Field(description="ID of the person to merge in and then delete")


class PersonMergeResult(BaseModel):
    """Summary of what a merge moved."""

    person_id: str = Field(description="The surviving person")
    faces_moved: int = 0
    matches_moved: int = 0
    event_participants_moved: int = 0
    comments_moved: int = 0
    mentions_moved: int = 0
    relationships_moved: int = 0
    relationship_candidates_moved: int = 0
    entity_matches_moved: int = 0


class Person(PersonBase):
    """Person model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Jane Doe",
                "aliases": ["J. Doe"],
                "notes": "Appears in multiple datasets",
                "tags": ["person-of-interest"],
                "dateOfBirth": None,
                "sex": None,
                "isVerified": True,
                "source": "manual",
                "dateCreated": "2024-01-01T12:00:00Z",
                "dateUpdated": "2024-01-02T12:00:00Z",
            }
        },
    }


class PersonSearchParameters(PageParams):
    """Parameters for listing/searching persons."""

    query: str | None = Field(default=None, description="Search name/aliases/notes")
    tags: list[str] | None = Field(default=None, description="Tags to filter")
    is_verified: bool | None = Field(default=None, description="Filter by verification status")
    source: PersonSource | None = Field(
        default=None, description="Filter by how the record was created (e.g. face_clustering for unnamed clusters)"
    )
    unnamed: bool | None = Field(
        default=None, description="True = only persons with no name yet; False = only named persons"
    )
    limit: int = Field(default=10, ge=1, le=100)
    sort_by: PersonSortField = Field(default=PersonSortField.DATE_UPDATED)


class PaginatedPersonsResponse(PaginatedResponse):
    """Paginated response for persons."""

    data: list[Person] = Field(description="List of persons")


class PersonSimilaritySearchRequest(BaseModel):
    """Search request for persons whose representative faces match a query face.

    A person matches if the query embedding is close enough to *any* of
    their representative faces (see `Face.is_representative`) — there is no
    single centroid embedding per person. Used by the matching pipeline to
    find candidate identities for a newly detected face before creating a
    FaceMatch for analyst review.
    """

    embedding: FaceEmbedding = Field(description="Face embedding to search")
    min_similarity: float | None = Field(default=None, ge=0, le=1)
    limit: int = Field(default=10, ge=1, le=100)


class PersonSimilarityResult(Person):
    """A person returned from a KNN search, carrying its best-matching similarity.

    `similarity_score` and `matched_face_id` reflect whichever of the
    person's representative faces was closest to the query embedding.
    """

    similarity_score: float = Field(ge=0, le=1, description="Similarity of the best-matching representative face")
    matched_face_id: str = Field(description="ID of the representative face that produced this match")


class PaginatedPersonSimilarityResponse(PaginatedResponse):
    """Paginated response for person similarity search."""

    data: list[PersonSimilarityResult] = Field(description="List of persons with similarity scores")


class PersonMergeSuggestion(Person):
    """Another person whose representative faces look like a given person's.

    `similarity_score` is the strongest match between any representative face
    of this person and any representative face of the reference person -- i.e.
    how likely they are the same identity and should be merged.
    """

    similarity_score: float = Field(
        ge=0, le=1, description="Best representative-face similarity to the reference person"
    )
