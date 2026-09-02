"""Type-specific detail for an `entity` of type organization (1:1 with `entity`)."""

from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel


class OrganizationBase(BaseModel):
    """Base organization detail schema."""

    entity_id: str = Field(description="The entity node this detail belongs to")
    legal_name: str | None = Field(default=None, description="Registered/legal name, if known")
    aliases: list[str] = Field(default_factory=list, description="Trade names and abbreviations")
    org_type: str | None = Field(default=None, description="e.g. company, agency, ngo, unit")
    country: str | None = Field(default=None)
    notes: str | None = Field(default=None)


class OrganizationCreate(OrganizationBase):
    """Organization detail creation schema."""

    pass


class OrganizationUpdate(BaseModel):
    """Organization detail update schema."""

    legal_name: str | None = Field(default=None)
    aliases: list[str] | None = Field(default=None)
    org_type: str | None = Field(default=None)
    country: str | None = Field(default=None)
    notes: str | None = Field(default=None)


class Organization(OrganizationBase):
    """Organization detail model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}
