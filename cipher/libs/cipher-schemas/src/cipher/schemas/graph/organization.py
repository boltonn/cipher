"""Type-specific detail for an `entity` of type organization (1:1 with `entity`)."""

from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas.graph.entity import EntitySummary
from cipher.schemas.graph.ontology import RelationshipType


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
    notes: str | None = Field(default=None)


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
    notes: str | None = Field(default=None)


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
