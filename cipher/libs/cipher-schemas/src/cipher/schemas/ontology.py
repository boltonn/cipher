"""Code-first ontology registry for the entity layer.

This module is the single extension point for the knowledge graph. Adding a
new entity type, selector kind, or relationship type is an enum member plus a
spec entry here -- no schema migration is required unless a new *structured*
filter/sort column is wanted on a detail table.

The registry also feeds the chat agent: `ontology_summary_for_llm` renders a
compact catalog that is injected into the agent instructions so the model
knows which types and relationships exist.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class EntityType(StrEnum):
    """Top-level kind of a graph node."""

    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    SELECTOR = "selector"


class EntitySource(StrEnum):
    """How an entity node came to exist."""

    EXTRACTION = "extraction"
    MANUAL = "manual"
    IMPORT = "import"
    FACE_CLUSTERING = "face_clustering"


class SelectorKind(StrEnum):
    """A strong, typed identifier that resolves to a single real-world thing."""

    PHONE = "phone"
    EMAIL = "email"
    PASSPORT = "passport"
    NATIONAL_ID = "national_id"
    IMEI = "imei"
    IBAN = "iban"
    HANDLE = "handle"
    CRYPTO_ADDRESS = "crypto_address"
    LICENSE_PLATE = "license_plate"


class LocationSource(StrEnum):
    """Where a location's coordinates/address came from."""

    NAMED_MENTION = "named_mention"
    EXIF = "exif"
    GEOCODED = "geocoded"
    DEVICE_GPS = "device_gps"


class RelationshipType(StrEnum):
    """A typed edge between two entity nodes."""

    HAS_SELECTOR = "has_selector"
    MEMBER_OF = "member_of"
    EMPLOYED_BY = "employed_by"
    PART_OF = "part_of"
    SUBSIDIARY_OF = "subsidiary_of"
    LOCATED_IN = "located_in"
    COMMUNICATES_WITH = "communicates_with"
    FAMILY_OF = "family_of"
    ASSOCIATE_OF = "associate_of"
    SAME_AS = "same_as"
    OWNS = "owns"


class RelationshipSource(StrEnum):
    """How a confirmed edge was established."""

    MANUAL = "manual"
    EXTRACTION = "extraction"
    SELECTOR_INFERENCE = "selector_inference"
    CO_MENTION = "co_mention"
    IMPORT = "import"


class ResolutionPolicy(StrEnum):
    """How a mention of a given (type, attribute) becomes -- or doesn't become -- an entity."""

    BY_VALUE = "by_value"  # selectors: normalize + dedupe on the value, always resolves
    BY_NAME_MATCH = "by_name_match"  # persons/orgs: match an existing entity by name; don't auto-create a bare one
    BY_GEOCODE = "by_geocode"  # addresses: resolve only once coordinates exist
    MANUAL_ONLY = "manual_only"  # e.g. a facility name with no geolocation -- stays unresolved until an analyst or a later pass


@dataclass(frozen=True, slots=True)
class TypeSpec:
    """Static description of one entity type."""

    entity_type: EntityType
    label_singular: str
    label_plural: str
    description: str
    allowed_selector_kinds: frozenset[SelectorKind] = field(default_factory=frozenset)
    # Attributes a NER mention can fill for this type. A mention asserts
    # `entity.<attribute> = normalized_value`, grounded at a span.
    mention_attributes: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class MentionTarget:
    """What a raw extractor label means: the entity attribute it fills, and how it resolves."""

    entity_type: EntityType
    attribute: str
    resolution: ResolutionPolicy
    selector_kind: SelectorKind | None = None


@dataclass(frozen=True, slots=True)
class RelationshipSpec:
    """Static description of one relationship type, including its endpoint constraints."""

    relationship_type: RelationshipType
    directed: bool
    symmetric: bool
    allowed_src: frozenset[EntityType]
    allowed_dst: frozenset[EntityType]
    description: str
    inverse_label: str | None = None


_ACTOR_TYPES = frozenset({EntityType.PERSON, EntityType.ORGANIZATION})
# A communication endpoint is an actor, or -- when the actor is unknown -- the
# bare selector it was sent from/to (an email address, a phone number).
_COMMS_ENDPOINT_TYPES = _ACTOR_TYPES | {EntityType.SELECTOR}
_ALL_TYPES = frozenset(EntityType)


ONTOLOGY: dict[EntityType, TypeSpec] = {
    EntityType.PERSON: TypeSpec(
        entity_type=EntityType.PERSON,
        label_singular="person",
        label_plural="people",
        description="A real-world individual of interest.",
        allowed_selector_kinds=frozenset(
            {
                SelectorKind.PHONE,
                SelectorKind.EMAIL,
                SelectorKind.PASSPORT,
                SelectorKind.NATIONAL_ID,
                SelectorKind.HANDLE,
                SelectorKind.IBAN,
                SelectorKind.CRYPTO_ADDRESS,
            }
        ),
        mention_attributes=frozenset({"name", "alias", "date_of_birth", "nationality"}),
    ),
    EntityType.ORGANIZATION: TypeSpec(
        entity_type=EntityType.ORGANIZATION,
        label_singular="organization",
        label_plural="organizations",
        description="A company, agency, unit, or other named group; may contain sub-units.",
        allowed_selector_kinds=frozenset(
            {SelectorKind.PHONE, SelectorKind.EMAIL, SelectorKind.IBAN, SelectorKind.HANDLE}
        ),
        mention_attributes=frozenset({"name", "alias"}),
    ),
    EntityType.LOCATION: TypeSpec(
        entity_type=EntityType.LOCATION,
        label_singular="location",
        label_plural="locations",
        description="A place: an address, a named place, or a geolocation from text or EXIF.",
        mention_attributes=frozenset({"name", "address"}),
    ),
    EntityType.SELECTOR: TypeSpec(
        entity_type=EntityType.SELECTOR,
        label_singular="selector",
        label_plural="selectors",
        description="A strong typed identifier (phone, email, passport, IMEI, IBAN, handle, ...).",
        # `selector_kind` is the `.type` (phone/email/...); `normalized_value` is the `.value`.
        mention_attributes=frozenset({"value"}),
    ),
}


def attributes_for(entity_type: EntityType) -> frozenset[str]:
    """The set of attributes a mention can assert for an entity of this type."""
    spec = ONTOLOGY.get(entity_type)
    return spec.mention_attributes if spec else frozenset()


RELATIONSHIPS: dict[RelationshipType, RelationshipSpec] = {
    RelationshipType.HAS_SELECTOR: RelationshipSpec(
        relationship_type=RelationshipType.HAS_SELECTOR,
        directed=True,
        symmetric=False,
        allowed_src=_ACTOR_TYPES,
        allowed_dst=frozenset({EntityType.SELECTOR}),
        inverse_label="selector_of",
        description="An actor uses this selector (phone/email/passport/...).",
    ),
    RelationshipType.MEMBER_OF: RelationshipSpec(
        relationship_type=RelationshipType.MEMBER_OF,
        directed=True,
        symmetric=False,
        allowed_src=frozenset({EntityType.PERSON}),
        allowed_dst=frozenset({EntityType.ORGANIZATION}),
        inverse_label="has_member",
        description="A person belongs to an organization.",
    ),
    RelationshipType.EMPLOYED_BY: RelationshipSpec(
        relationship_type=RelationshipType.EMPLOYED_BY,
        directed=True,
        symmetric=False,
        allowed_src=frozenset({EntityType.PERSON}),
        allowed_dst=frozenset({EntityType.ORGANIZATION}),
        inverse_label="employs",
        description="A person is employed by an organization.",
    ),
    RelationshipType.PART_OF: RelationshipSpec(
        relationship_type=RelationshipType.PART_OF,
        directed=True,
        symmetric=False,
        allowed_src=frozenset({EntityType.ORGANIZATION}),
        allowed_dst=frozenset({EntityType.ORGANIZATION}),
        inverse_label="has_part",
        description="An organization sub-unit (e.g. a regional office) is part of a parent org.",
    ),
    RelationshipType.SUBSIDIARY_OF: RelationshipSpec(
        relationship_type=RelationshipType.SUBSIDIARY_OF,
        directed=True,
        symmetric=False,
        allowed_src=frozenset({EntityType.ORGANIZATION}),
        allowed_dst=frozenset({EntityType.ORGANIZATION}),
        inverse_label="parent_of",
        description="An organization is a subsidiary of another.",
    ),
    RelationshipType.LOCATED_IN: RelationshipSpec(
        relationship_type=RelationshipType.LOCATED_IN,
        directed=True,
        symmetric=False,
        allowed_src=frozenset({EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION}),
        allowed_dst=frozenset({EntityType.LOCATION}),
        inverse_label="contains",
        description="An entity is located at / within a location.",
    ),
    RelationshipType.COMMUNICATES_WITH: RelationshipSpec(
        relationship_type=RelationshipType.COMMUNICATES_WITH,
        directed=False,
        symmetric=True,
        allowed_src=_COMMS_ENDPOINT_TYPES,
        allowed_dst=_COMMS_ENDPOINT_TYPES,
        description=(
            "Two endpoints are recorded communicating (email, calls, messages). Endpoints are "
            "people/orgs when resolved, otherwise the bare email or phone selector."
        ),
    ),
    RelationshipType.FAMILY_OF: RelationshipSpec(
        relationship_type=RelationshipType.FAMILY_OF,
        directed=False,
        symmetric=True,
        allowed_src=frozenset({EntityType.PERSON}),
        allowed_dst=frozenset({EntityType.PERSON}),
        description="Two people are family.",
    ),
    RelationshipType.ASSOCIATE_OF: RelationshipSpec(
        relationship_type=RelationshipType.ASSOCIATE_OF,
        directed=False,
        symmetric=True,
        allowed_src=_ACTOR_TYPES,
        allowed_dst=_ACTOR_TYPES,
        description="Two actors are associated, often inferred from co-mention. Excluded from default graph traversal.",
    ),
    RelationshipType.SAME_AS: RelationshipSpec(
        relationship_type=RelationshipType.SAME_AS,
        directed=False,
        symmetric=True,
        allowed_src=_ALL_TYPES,
        allowed_dst=_ALL_TYPES,
        description="Two entity nodes are asserted to be the same real-world thing.",
    ),
    RelationshipType.OWNS: RelationshipSpec(
        relationship_type=RelationshipType.OWNS,
        directed=True,
        symmetric=False,
        allowed_src=_ACTOR_TYPES,
        allowed_dst=_ALL_TYPES,
        inverse_label="owned_by",
        description="An actor owns an asset, account, or other entity.",
    ),
}

# Co-mention style edges that should not be walked by default relationship traversal,
# because they make the graph dense and low-signal for multi-hop questions.
LOW_SIGNAL_RELATIONSHIPS: frozenset[RelationshipType] = frozenset({RelationshipType.ASSOCIATE_OF})


# The heart of NER resolution: a raw extractor label -> the entity attribute it
# fills and how that resolves. A mention asserts `entity.<attribute> = value`;
# `resolution` decides whether/when that mention becomes (or attaches to) an
# entity. Extend this alongside the enums so a new label flows through.
LABEL_TO_MENTION_TARGET: dict[str, MentionTarget] = {
    "person": MentionTarget(EntityType.PERSON, "name", ResolutionPolicy.BY_NAME_MATCH),
    "organization": MentionTarget(EntityType.ORGANIZATION, "name", ResolutionPolicy.BY_NAME_MATCH),
    "company": MentionTarget(EntityType.ORGANIZATION, "name", ResolutionPolicy.BY_NAME_MATCH),
    "location": MentionTarget(EntityType.LOCATION, "name", ResolutionPolicy.MANUAL_ONLY),
    "facility": MentionTarget(EntityType.LOCATION, "name", ResolutionPolicy.MANUAL_ONLY),
    "address": MentionTarget(EntityType.LOCATION, "address", ResolutionPolicy.BY_GEOCODE),
    "phone number": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorKind.PHONE
    ),
    "email address": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorKind.EMAIL
    ),
    "passport number": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorKind.PASSPORT
    ),
    "national id number": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorKind.NATIONAL_ID
    ),
    "bank account number": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorKind.IBAN
    ),
    "social media handle": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorKind.HANDLE
    ),
}

# Derived views kept for callers that only need one axis.
NER_LABEL_TO_TYPE: dict[str, EntityType] = {
    label: t.entity_type for label, t in LABEL_TO_MENTION_TARGET.items()
}
NER_LABEL_TO_SELECTOR_KIND: dict[str, SelectorKind] = {
    label: t.selector_kind
    for label, t in LABEL_TO_MENTION_TARGET.items()
    if t.selector_kind is not None
}


def mention_target(label: str) -> MentionTarget | None:
    """Resolve a raw extractor label to its (entity_type, attribute, resolution)."""
    return LABEL_TO_MENTION_TARGET.get(label.strip().lower())


def default_ner_labels() -> list[str]:
    """The default zero-shot *entity* label set, derived from the ontology."""
    return list(LABEL_TO_MENTION_TARGET.keys())


def default_relation_labels() -> list[str]:
    """The default zero-shot *relation* label set for GLiREL-style extraction.

    Human-readable phrasings of the directed relationship types; map a
    prediction back with `RELATION_LABEL_TO_TYPE`.
    """
    return list(RELATION_LABEL_TO_TYPE.keys())


RELATION_LABEL_TO_TYPE: dict[str, RelationshipType] = {
    "has phone or email": RelationshipType.HAS_SELECTOR,
    "member of": RelationshipType.MEMBER_OF,
    "employed by": RelationshipType.EMPLOYED_BY,
    "part of organization": RelationshipType.PART_OF,
    "subsidiary of": RelationshipType.SUBSIDIARY_OF,
    "located in": RelationshipType.LOCATED_IN,
    "communicates with": RelationshipType.COMMUNICATES_WITH,
    "family of": RelationshipType.FAMILY_OF,
    "associate of": RelationshipType.ASSOCIATE_OF,
    "owns": RelationshipType.OWNS,
}


def validate_relationship(
    *, relationship_type: RelationshipType, src_type: EntityType, dst_type: EntityType
) -> None:
    """Check that an edge of this type is allowed between these endpoint types.

    Args:
        relationship_type: The edge type.
        src_type: Entity type of the edge source.
        dst_type: Entity type of the edge destination.

    Raises:
        ValueError: If the relationship type is unknown or the endpoints are not permitted.
    """
    spec = RELATIONSHIPS.get(relationship_type)
    if spec is None:
        raise ValueError(f"Unknown relationship type: {relationship_type}")
    if src_type not in spec.allowed_src or dst_type not in spec.allowed_dst:
        if spec.symmetric and dst_type in spec.allowed_src and src_type in spec.allowed_dst:
            return
        raise ValueError(
            f"Relationship '{relationship_type}' is not allowed from '{src_type}' to '{dst_type}'"
        )


def ontology_summary_for_llm() -> str:
    """Render a compact catalog of entity and relationship types for agent instructions."""
    lines = ["Entity types:"]
    for spec in ONTOLOGY.values():
        lines.append(f"  - {spec.entity_type}: {spec.description}")
    lines.append("Relationship types (source -> destination):")
    for spec in RELATIONSHIPS.values():
        src = "|".join(sorted(t.value for t in spec.allowed_src))
        dst = "|".join(sorted(t.value for t in spec.allowed_dst))
        lines.append(f"  - {spec.relationship_type} ({src} -> {dst}): {spec.description}")
    return "\n".join(lines)
