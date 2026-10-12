"""Type-specific detail for an `entity` of type organization (1:1 with `entity`)."""

from datetime import datetime

from pydantic import Field, SerializationInfo, field_serializer

from cipher.schemas._base.base import BaseModel, StrEnum, camelize_keys
from cipher.schemas._base.common import PageParams, PaginatedResponse, SortOrder
from cipher.schemas.graph.entity import EntitySummary
from cipher.schemas.graph.entity_relationship import RelationshipCandidateMethod
from cipher.schemas.graph.ontology import EntityType, RelationshipSource, RelationshipType

# Edges that put a person *inside* an organization; any other person<->org edge only connects them.
MEMBERSHIP_RELATIONSHIPS = (RelationshipType.EMPLOYED_BY, RelationshipType.MEMBER_OF)


class OrganizationBase(BaseModel):
    """Base organization detail schema."""

    entity_id: str = Field(description="The entity node this detail belongs to")
    legal_name: str | None = Field(default=None, description="Registered/legal name, if known")
    aliases: list[str] = Field(default_factory=list, description="Trade names and abbreviations")
    category: str | None = Field(
        default=None, description="What kind of organization, e.g. company, agency, ngo, division, office, branch"
    )
    parent_id: str | None = Field(
        default=None, description="Entity id of the organization this one is a unit of (mirrored as a part_of edge)"
    )
    country: str | None = Field(default=None)


class OrganizationCreate(OrganizationBase):
    """Organization detail creation schema."""

    pass


class OrganizationUpdate(BaseModel):
    """Organization detail update schema."""

    legal_name: str | None = Field(default=None)
    aliases: list[str] | None = Field(default=None)
    category: str | None = Field(default=None)
    parent_id: str | None = Field(default=None)
    country: str | None = Field(default=None)


class Organization(OrganizationBase):
    """Organization detail model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}


class OrganizationMember(BaseModel):
    """A person tied to an organization by an `employed_by` / `member_of` edge."""

    entity: EntitySummary
    relationship_type: RelationshipType
    role: str | None = Field(default=None)


class OrganizationStructure(BaseModel):
    """An organization's place in the hierarchy plus what hangs off it (all read from edges)."""

    ancestors: list[EntitySummary] = Field(default_factory=list, description="Parent first, then its parent, ...")
    children: list[EntitySummary] = Field(default_factory=list, description="Sub-units (`part_of` this one)")
    locations: list[EntitySummary] = Field(default_factory=list, description="`located_in` targets")
    members: list[OrganizationMember] = Field(default_factory=list, description="People employed by / members of it")


class OrganizationTreeNode(BaseModel):
    """One organization in a hierarchy, pointing at its parent (`part_of`)."""

    entity: EntitySummary
    parent_id: str | None = Field(default=None, description="Entity id of the parent unit; None for the root")
    suggestion_id: str | None = Field(
        default=None, description="Pending `part_of` suggestion that would attach this unit; None once confirmed"
    )
    category: str | None = Field(default=None)
    member_count: int = Field(default=0, description="People employed by / members of this unit directly")
    connected_count: int = Field(default=0, description="People tied to this unit by any other edge")


class OrganizationTree(BaseModel):
    """The whole hierarchy an organization sits in, from its top-most ancestor down (flat, parent-linked)."""

    root_id: str
    nodes: list[OrganizationTreeNode]


class OrganizationAffiliation(StrEnum):
    """How a person relates to an organization unit."""

    MEMBER = "member"
    CONNECTED = "connected"


class OrganizationPeopleSortField(StrEnum):
    DISPLAY_NAME = "display_name"
    ROLE = "role"
    UNIT = "unit"
    RELATIONSHIP_TYPE = "relationship_type"
    SOURCE = "source"
    MENTION_COUNT = "mention_count"
    FILE_COUNT = "file_count"
    DATE_OBSERVED_END = "date_observed_end"


class OrganizationPeopleParameters(PageParams):
    """Filters for the people within / connected to an organization unit."""

    include_sub_units: bool = Field(default=True, description="Also include people on every unit below this one")
    affiliation: OrganizationAffiliation | None = Field(default=None, description="None returns both")
    relationship_types: list[RelationshipType] | None = Field(default=None)
    sources: list[RelationshipSource] | None = Field(default=None)
    query: str | None = Field(default=None, description="Substring match on the person's name")
    role: str | None = Field(default=None, description="Substring match on the edge's role/title")
    unit: str | None = Field(default=None, description="Substring match on the unit's name")
    is_verified: bool | None = Field(default=None)
    limit: int = Field(default=50, ge=1, le=200)
    sort_by: OrganizationPeopleSortField = Field(default=OrganizationPeopleSortField.DISPLAY_NAME)
    sort_order: SortOrder = Field(default=SortOrder.ASC)


class OrganizationPerson(BaseModel):
    """One person<->unit edge: a person can appear once per unit/edge they hold."""

    relationship_id: str
    person: EntitySummary
    unit: EntitySummary
    relationship_type: RelationshipType
    affiliation: OrganizationAffiliation
    role: str | None = Field(default=None)
    source: RelationshipSource
    mention_count: int = Field(default=0, description="Mentions resolved to the person")
    file_count: int = Field(default=0, description="Distinct files those mentions are in")
    date_observed_start: datetime | None = Field(default=None)
    date_observed_end: datetime | None = Field(default=None)


class OrganizationSuggestion(BaseModel):
    """A pending suggestion on an organization unit, awaiting review.

    `entity` is a person (`employed_by` / `member_of` the unit) or a sub-unit (`part_of` it).
    """

    candidate_id: str
    entity: EntitySummary
    unit: EntitySummary
    relationship_type: RelationshipType
    method: RelationshipCandidateMethod
    role: str | None = Field(default=None)
    confidence: float
    explanation: dict | None = Field(default=None, description="Why it was proposed (e.g. the email-domain numbers)")

    @field_serializer("explanation")
    def _camel_explanation(self, explanation: dict | None, info: SerializationInfo) -> dict | None:
        return camelize_keys(explanation) if explanation is not None and info.by_alias else explanation


class PaginatedOrganizationPeople(PaginatedResponse):
    data: list[OrganizationPerson]


class NameSuggestionSide(BaseModel):
    """One end of a name-level suggestion: a name as extracted, and what it might be."""

    name: str = Field(description="The name as written (most common spelling)")
    normalized_value: str = Field(description="The name group's key (what resolution groups by)")
    entity_type: EntityType
    entity: EntitySummary | None = Field(default=None, description="Already resolved to this entity")
    entity_is_provisional: bool = Field(default=False, description="`entity` was auto-created, not yet confirmed")
    guess: EntitySummary | None = Field(default=None, description="The resolver's best guess (Resolve queue)")
    guess_score: float | None = Field(default=None)
    owner: EntitySummary | None = Field(
        default=None, description="The person who owns the sending address the signature was confirmed against"
    )
    owner_address: str | None = Field(default=None)
    unresolved_mentions: int = Field(default=0, description="Unresolved mentions of this name in the dataset")


class NameSuggestion(BaseModel):
    """A signature / membership relationship whose names are not both settled yet (one row per name pair)."""

    dataset_id: str
    extractor: str = Field(description="What produced it: `signature` or `membership`")
    relationship_type: RelationshipType
    source: NameSuggestionSide
    target: NameSuggestionSide
    role: str | None = Field(default=None)
    sightings: int = Field(description="Emails that state it")
    mention_relationship_ids: list[str] = Field(description="The mention relations behind it (for sources)")


class NameSuggestionChoice(BaseModel):
    """The reviewer's answer for one side: an existing entity, or None to create one named `display_name`."""

    normalized_value: str
    entity_type: EntityType
    entity_id: str | None = Field(default=None)
    display_name: str = Field(max_length=512)


class NameSuggestionAccept(BaseModel):
    """Accept a name-level suggestion: settle both names, confirm the entities, and add the edge."""

    dataset_id: str
    relationship_type: RelationshipType
    source: NameSuggestionChoice
    target: NameSuggestionChoice
    role: str | None = Field(default=None)
    mention_relationship_ids: list[str] = Field(min_length=1, max_length=1000)


class NameSuggestionAccepted(BaseModel):
    source_entity_id: str
    target_entity_id: str
    created_entity_ids: list[str] = Field(default_factory=list)


class NameSuggestionDismiss(BaseModel):
    """Dismiss a name-level suggestion; its names stay in the Resolve queue."""

    mention_relationship_ids: list[str] = Field(min_length=1, max_length=1000)
