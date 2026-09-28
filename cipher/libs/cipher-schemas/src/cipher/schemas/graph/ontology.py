"""Code-first ontology registry for the entity layer.

This module is the single extension point for the knowledge graph. Adding a
new entity type, selector kind, or relationship type is an enum member plus a
spec entry here -- no schema migration is required unless a new *structured*
filter/sort column is wanted on a detail table.

The registry also feeds the chat agent: `ontology_summary_for_llm` renders a
compact catalog that is injected into the agent instructions so the model
knows which types and relationships exist.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import Field

from cipher.schemas._base.base import BaseModel


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


class SelectorType(StrEnum):
    """The broad family of a selector -- always present on a selector row.

    The specific provider / network (Telegram, Instagram, BTC, ETH, ...) is the
    optional ``SelectorSubtype``. Query one axis or the other:
    ``selector_type == CRYPTO_ADDRESS`` for all crypto, ``selector_subtype ==
    TELEGRAM`` for one platform.
    """

    PHONE = "phone"
    EMAIL = "email"
    IP = "ip"
    IBAN = "iban"
    BANK_CARD = "bank_card"
    PASSPORT = "passport"
    NATIONAL_ID = "national_id"
    IMEI = "imei"
    IMSI = "imsi"
    SOCIAL_HANDLE = "social_handle"
    CRYPTO_ADDRESS = "crypto_address"
    LICENSE_PLATE = "license_plate"


class SelectorSubtype(StrEnum):
    """The specific provider / network / scheme within a ``SelectorType``. Optional."""

    # social_handle
    TELEGRAM = "telegram"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    WHATSAPP = "whatsapp"
    SIGNAL = "signal"
    TWITTER = "twitter"
    TIKTOK = "tiktok"
    VK = "vk"
    ODNOKLASSNIKI = "odnoklassniki"
    WECHAT = "wechat"
    QQ = "qq"
    WEIBO = "weibo"
    DOUYIN = "douyin"
    SOROUSH = "soroush"
    BALE = "bale"
    RUBIKA = "rubika"
    EITAA = "eitaa"

    # crypto_address
    BTC_ADDRESS = "btc_address"
    ETH_ADDRESS = "eth_address"
    XMR_ADDRESS = "xmr_address"
    TRON_ADDRESS = "tron_address"

    # national_id
    RU_INN = "ru_inn"
    RU_SNILS = "ru_snils"
    CN_RIC = "cn_ric"
    IR_CODE_MELLI = "ir_code_melli"


SELECTOR_SUBTYPES: dict[SelectorType, frozenset[SelectorSubtype]] = {
    SelectorType.SOCIAL_HANDLE: frozenset(
        {
            SelectorSubtype.TELEGRAM,
            SelectorSubtype.INSTAGRAM,
            SelectorSubtype.FACEBOOK,
            SelectorSubtype.WHATSAPP,
            SelectorSubtype.SIGNAL,
            SelectorSubtype.TWITTER,
            SelectorSubtype.TIKTOK,
            SelectorSubtype.VK,
            SelectorSubtype.ODNOKLASSNIKI,
            SelectorSubtype.WECHAT,
            SelectorSubtype.QQ,
            SelectorSubtype.WEIBO,
            SelectorSubtype.DOUYIN,
            SelectorSubtype.SOROUSH,
            SelectorSubtype.BALE,
            SelectorSubtype.RUBIKA,
            SelectorSubtype.EITAA,
        }
    ),
    SelectorType.CRYPTO_ADDRESS: frozenset(
        {
            SelectorSubtype.BTC_ADDRESS,
            SelectorSubtype.ETH_ADDRESS,
            SelectorSubtype.XMR_ADDRESS,
            SelectorSubtype.TRON_ADDRESS,
        }
    ),
    SelectorType.NATIONAL_ID: frozenset(
        {
            SelectorSubtype.RU_INN,
            SelectorSubtype.RU_SNILS,
            SelectorSubtype.CN_RIC,
            SelectorSubtype.IR_CODE_MELLI,
        }
    ),
}

SUBTYPE_TO_TYPE: dict[SelectorSubtype, SelectorType] = {
    sub: typ for typ, subs in SELECTOR_SUBTYPES.items() for sub in subs
}


def selector_type_of(subtype: SelectorSubtype) -> SelectorType:
    """The ``SelectorType`` a subtype rolls up to."""
    return SUBTYPE_TO_TYPE[subtype]


class LocationSource(StrEnum):
    """Where a location's coordinates/address came from."""

    NAMED_MENTION = "named_mention"
    TEXT_MENTION = "text_mention"
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
    APPEARS_IN_PHOTO_WITH = "appears_in_photo_with"
    SAME_AS = "same_as"
    OWNS = "owns"


class RelationshipSource(StrEnum):
    """How a confirmed edge was established."""

    MANUAL = "manual"
    EXTRACTION = "extraction"
    SELECTOR_INFERENCE = "selector_inference"
    CO_MENTION = "co_mention"
    FACE_COOCCURRENCE = "face_cooccurrence"
    IMPORT = "import"


class FamilyRole(StrEnum):
    """How the source person stands to the target on a ``family_of`` edge.

    Stored as ``attributes['role']``; read "src is <role> of dst". Roles are
    gender-neutral (no father/son) -- the same real relationship is one edge, and
    the far end is rendered from ``FAMILY_ROLE_INVERSE`` rather than a second role.
    """

    PARENT = "parent"
    CHILD = "child"
    SIBLING = "sibling"
    SPOUSE = "spouse"
    GRANDPARENT = "grandparent"
    GRANDCHILD = "grandchild"
    AUNT_UNCLE = "aunt_uncle"
    NIECE_NEPHEW = "niece_nephew"
    COUSIN = "cousin"
    RELATIVE = "relative"


# The inverse role seen from the target's side of a family_of edge.
FAMILY_ROLE_INVERSE: dict[FamilyRole, FamilyRole] = {
    FamilyRole.PARENT: FamilyRole.CHILD,
    FamilyRole.CHILD: FamilyRole.PARENT,
    FamilyRole.GRANDPARENT: FamilyRole.GRANDCHILD,
    FamilyRole.GRANDCHILD: FamilyRole.GRANDPARENT,
    FamilyRole.AUNT_UNCLE: FamilyRole.NIECE_NEPHEW,
    FamilyRole.NIECE_NEPHEW: FamilyRole.AUNT_UNCLE,
    FamilyRole.SIBLING: FamilyRole.SIBLING,
    FamilyRole.SPOUSE: FamilyRole.SPOUSE,
    FamilyRole.COUSIN: FamilyRole.COUSIN,
    FamilyRole.RELATIVE: FamilyRole.RELATIVE,
}


# The typed enum an edge's ``attributes['role']`` must belong to, per relationship
# type. Absent = that edge type carries no role. Keep in sync with the frontend.
RELATIONSHIP_ROLE_ENUM: dict[RelationshipType, type[StrEnum]] = {
    RelationshipType.FAMILY_OF: FamilyRole,
}


class ResolutionPolicy(StrEnum):
    """How a mention of a given (type, attribute) becomes -- or doesn't become -- an entity."""

    BY_VALUE = "by_value"  # selectors: normalize + dedupe on the value, always resolves
    BY_NAME_MATCH = "by_name_match"  # persons/orgs: match an existing entity by name; don't auto-create a bare one
    BY_GEOCODE = "by_geocode"  # addresses: resolve only once coordinates exist
    MANUAL_ONLY = (
        "manual_only"  # e.g. a facility name with no geolocation -- stays unresolved until an analyst or a later pass
    )


@dataclass(frozen=True, slots=True)
class TypeSpec:
    """Static description of one entity type."""

    entity_type: EntityType
    label_singular: str
    label_plural: str
    description: str
    allowed_selector_types: frozenset[SelectorType] = field(default_factory=frozenset)
    # Attributes a NER mention can fill for this type. A mention asserts
    # `entity.<attribute> = normalized_value`, grounded at a span.
    mention_attributes: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class MentionTarget:
    """What a raw extractor label means: the entity attribute it fills, and how it resolves."""

    entity_type: EntityType
    attribute: str
    resolution: ResolutionPolicy
    selector_type: SelectorType | None = None


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
        allowed_selector_types=frozenset(
            {
                SelectorType.PHONE,
                SelectorType.EMAIL,
                SelectorType.SOCIAL_HANDLE,
                SelectorType.CRYPTO_ADDRESS,
                SelectorType.IBAN,
                SelectorType.BANK_CARD,
                SelectorType.PASSPORT,
                SelectorType.NATIONAL_ID,
            }
        ),
        mention_attributes=frozenset({"name", "date_of_birth", "nationality"}),
    ),
    EntityType.ORGANIZATION: TypeSpec(
        entity_type=EntityType.ORGANIZATION,
        label_singular="organization",
        label_plural="organizations",
        description="A company, agency, unit, or other named group; may contain sub-units.",
        allowed_selector_types=frozenset(
            {
                SelectorType.PHONE,
                SelectorType.EMAIL,
                SelectorType.SOCIAL_HANDLE,
                SelectorType.IBAN,
                SelectorType.BANK_CARD,
                SelectorType.IP,
            }
        ),
        mention_attributes=frozenset({"name"}),
    ),
    EntityType.LOCATION: TypeSpec(
        entity_type=EntityType.LOCATION,
        label_singular="location",
        label_plural="locations",
        description="A place: an address, a named place, or a geolocation from text or EXIF.",
        mention_attributes=frozenset({"name", "address", "coordinate"}),
    ),
    EntityType.SELECTOR: TypeSpec(
        entity_type=EntityType.SELECTOR,
        label_singular="selector",
        label_plural="selectors",
        description="A strong typed identifier (phone, email, passport, IMEI, IBAN, handle, ...).",
        # `selector_type` is the `.type` (phone/email/...); `normalized_value` is the `.value`.
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
    RelationshipType.APPEARS_IN_PHOTO_WITH: RelationshipSpec(
        relationship_type=RelationshipType.APPEARS_IN_PHOTO_WITH,
        directed=False,
        symmetric=True,
        allowed_src=frozenset({EntityType.PERSON}),
        allowed_dst=frozenset({EntityType.PERSON}),
        description=(
            "Two people were detected in the same image by face recognition -- either "
            "face may still be an unconfirmed (pending) match. `weight` is the number of "
            "shared photos. Excluded from default graph traversal."
        ),
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
LOW_SIGNAL_RELATIONSHIPS: frozenset[RelationshipType] = frozenset(
    {RelationshipType.ASSOCIATE_OF, RelationshipType.APPEARS_IN_PHOTO_WITH}
)


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
    "coordinate": MentionTarget(EntityType.LOCATION, "coordinate", ResolutionPolicy.BY_GEOCODE),
    "phone number": MentionTarget(EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.PHONE),
    "email address": MentionTarget(EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.EMAIL),
    "ip address": MentionTarget(EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.IP),
    "passport number": MentionTarget(EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.PASSPORT),
    "national id number": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.NATIONAL_ID
    ),
    "imsi": MentionTarget(EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.IMSI),
    "bank account number": MentionTarget(EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.IBAN),
    "payment card number": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.BANK_CARD
    ),
    "social media handle": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.SOCIAL_HANDLE
    ),
    "cryptocurrency address": MentionTarget(
        EntityType.SELECTOR, "value", ResolutionPolicy.BY_VALUE, SelectorType.CRYPTO_ADDRESS
    ),
}

# Derived views kept for callers that only need one axis.
NER_LABEL_TO_TYPE: dict[str, EntityType] = {label: t.entity_type for label, t in LABEL_TO_MENTION_TARGET.items()}
NER_LABEL_TO_SELECTOR_TYPE: dict[str, SelectorType] = {
    label: t.selector_type for label, t in LABEL_TO_MENTION_TARGET.items() if t.selector_type is not None
}

# Resolution policy for a schema-aligned ``<entity_type>.<attribute>`` label --
# the tagset the supervised ``analytics/nerd`` model emits (e.g. ``person.name``,
# ``location.address``). Absent (type, attr) pairs fall back to ``MANUAL_ONLY``.
RESOLUTION_BY_TYPE_ATTR: dict[tuple[EntityType, str], ResolutionPolicy] = {
    (EntityType.PERSON, "name"): ResolutionPolicy.BY_NAME_MATCH,
    (EntityType.PERSON, "date_of_birth"): ResolutionPolicy.BY_NAME_MATCH,
    (EntityType.PERSON, "nationality"): ResolutionPolicy.BY_NAME_MATCH,
    (EntityType.ORGANIZATION, "name"): ResolutionPolicy.BY_NAME_MATCH,
    (EntityType.LOCATION, "name"): ResolutionPolicy.MANUAL_ONLY,
    (EntityType.LOCATION, "address"): ResolutionPolicy.BY_GEOCODE,
}

# Raw type tokens other people's NER models emit (CoNLL-2003, OntoNotes,
# spaCy, GLiNER prompts, WikiANN, ...) -> the canonical entity type. Anything
# here without an explicit attribute resolves to that type's primary attribute
# (``name`` for person/org/location). This is what lets a mention from a
# model CIPHER has never seen still land on an entity.
_EXTERNAL_TYPE_ALIASES: dict[str, EntityType] = {
    # person
    "per": EntityType.PERSON,
    "pers": EntityType.PERSON,
    "person": EntityType.PERSON,
    "people": EntityType.PERSON,
    "human": EntityType.PERSON,
    "individual": EntityType.PERSON,
    "name": EntityType.PERSON,
    "persname": EntityType.PERSON,
    "per_name": EntityType.PERSON,
    # organization
    "org": EntityType.ORGANIZATION,
    "orgs": EntityType.ORGANIZATION,
    "organization": EntityType.ORGANIZATION,
    "organisation": EntityType.ORGANIZATION,
    "company": EntityType.ORGANIZATION,
    "corp": EntityType.ORGANIZATION,
    "corporation": EntityType.ORGANIZATION,
    "institution": EntityType.ORGANIZATION,
    "agency": EntityType.ORGANIZATION,
    "group": EntityType.ORGANIZATION,
    "orgname": EntityType.ORGANIZATION,
    # location (named place -- GPE / LOC / FAC all fold here; admin level is a
    # geocode-time concern, not an NER-time one)
    "loc": EntityType.LOCATION,
    "location": EntityType.LOCATION,
    "place": EntityType.LOCATION,
    "gpe": EntityType.LOCATION,
    "geo": EntityType.LOCATION,
    "geoloc": EntityType.LOCATION,
    "fac": EntityType.LOCATION,
    "facility": EntityType.LOCATION,
    "building": EntityType.LOCATION,
    "city": EntityType.LOCATION,
    "country": EntityType.LOCATION,
    "state": EntityType.LOCATION,
    "province": EntityType.LOCATION,
    "region": EntityType.LOCATION,
    "territory": EntityType.LOCATION,
    "landmark": EntityType.LOCATION,
    "poi": EntityType.LOCATION,
    "locname": EntityType.LOCATION,
}
# Raw labels that specifically mean a postal address (LOCATION.address, not .name).
_EXTERNAL_ADDRESS_ALIASES: frozenset[str] = frozenset(
    {
        "address",
        "addr",
        "street address",
        "street_address",
        "postal address",
        "postal_address",
        "mailing address",
        "full address",
        "location.address",
        "loc.address",
        "gpe.address",
    }
)
# Raw attribute tokens -> canonical attribute name.
_EXTERNAL_ATTR_ALIASES: dict[str, str] = {
    "name": "name",
    "fullname": "name",
    "full_name": "name",
    "label": "name",
    "value": "name",
    "address": "address",
    "addr": "address",
    "street": "address",
    "dob": "date_of_birth",
    "birthdate": "date_of_birth",
    "date_of_birth": "date_of_birth",
    "nationality": "nationality",
    "citizenship": "nationality",
    "country_of_citizenship": "nationality",
}


def _normalize_label_key(label: str) -> str:
    """Lower-case, drop a ``B-``/``I-``/``E-``/``S-`` IOB prefix, unify separators to ``.``."""
    key = label.strip().lower()
    if len(key) > 2 and key[1] == "-" and key[0] in "bielsu":
        key = key[2:]
    return key.replace("::", ".").replace(":", ".").replace("/", ".").replace(" - ", ".").replace("__", ".")


def mention_target(label: str) -> MentionTarget | None:
    """Resolve *any* extractor's raw label to a ``(entity_type, attribute, resolution)``.

    Handled, in order:

    * the flat zero-shot labels this repo's own extractors emit (``person``,
      ``address``, ``phone number``, ...);
    * the schema-aligned ``<entity_type>.<attribute>`` form the supervised
      ``analytics/nerd`` model emits (``person.name``, ``location.address``);
    * an unfamiliar label from a third-party model -- CoNLL/OntoNotes/spaCy
      tags (``PER``, ``B-GPE``, ``ORG``), verbose names (``street address``),
      or ``TYPE.ATTR`` / ``TYPE:ATTR`` / ``TYPE/ATTR`` with a synonym on either
      side. Falls back to the type's ``name`` attribute when no attribute is given.

    Returns ``None`` only when nothing plausibly maps -- the caller then keeps
    the mention unresolved rather than guessing.
    """
    key = _normalize_label_key(label)

    hit = LABEL_TO_MENTION_TARGET.get(key)
    if hit is not None:
        return hit

    if key in _EXTERNAL_ADDRESS_ALIASES:
        return MentionTarget(EntityType.LOCATION, "address", ResolutionPolicy.BY_GEOCODE)

    type_str, sep, attr_str = key.partition(".")
    if not sep and "_" in key:
        # ``person_name`` / ``org_name`` -- but not ``date_of_birth``: only split
        # when the head is a recognised type token.
        head, _, tail = key.partition("_")
        if head in _EXTERNAL_TYPE_ALIASES or head in {e.value for e in EntityType}:
            type_str, sep, attr_str = head, "_", tail

    etype: EntityType | None = None
    try:
        etype = EntityType(type_str)
    except ValueError:
        etype = _EXTERNAL_TYPE_ALIASES.get(type_str)
    if etype is None:
        return None

    attr = "name"
    if sep and attr_str:
        attr = _EXTERNAL_ATTR_ALIASES.get(attr_str.replace(" ", "_"), attr_str)
    if attr not in attributes_for(etype):
        attr = "name" if "name" in attributes_for(etype) else next(iter(attributes_for(etype)), None)
    if attr is None:
        return None
    return MentionTarget(etype, attr, RESOLUTION_BY_TYPE_ATTR.get((etype, attr), ResolutionPolicy.MANUAL_ONLY))


# Whole-word tokens that mark a name as an organization rather than a person --
# legal forms, functional mailbox roles, and newsletter/automation senders.
_ORG_WORD_RE = re.compile(
    r"\b(inc|llc|ltd|l\.?p|corp|co|gmbh|s\.?a|plc|ag|nv|pty|group|holdings?|"
    r"team|support|sales|billing|accounts?|info|admin|hr|it|noreply|no-reply|"
    r"newsletter|digest|notifications?|updates?|alerts?|service|services|helpdesk|"
    r"care|mailer|marketing|news|store|shop|bank|company|foundation|institute|"
    r"university|college|school|dept|department|office|bureau|agency|ministry|"
    r"committee|council|association|society|federation|union|club|partners?|"
    r"solutions?|systems?|technologies|labs?|media|press|studio|studios)\b",
    re.IGNORECASE,
)
# Two or three Title-Case tokens (optional single-letter middle initial) and
# nothing else -- the shape of a personal name.
_PERSON_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,2}$")


def guess_actor_type(name: str) -> EntityType | None:
    """Heuristic person-vs-organization guess for a bare display name.

    Returns `PERSON` or `ORGANIZATION` only on a strong signal, else `None`
    (the analyst decides). Used to pre-select a choice in the review queue; it
    never resolves anything on its own.
    """
    text = (name or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if (
        _ORG_WORD_RE.search(text)
        or "&" in text
        or "@" in text
        or any(ch.isdigit() for ch in text)
        or lowered.startswith("the ")
        or (text.isupper() and len(text) > 1)
        or len(text.split()) >= 4
    ):
        return EntityType.ORGANIZATION
    if _PERSON_RE.match(text):
        return EntityType.PERSON
    return None


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


def validate_relationship(*, relationship_type: RelationshipType, src_type: EntityType, dst_type: EntityType) -> None:
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
        raise ValueError(f"Relationship '{relationship_type}' is not allowed from '{src_type}' to '{dst_type}'")


RELATIONSHIP_LABELS: dict[RelationshipType, str] = {
    RelationshipType.HAS_SELECTOR: "Has selector",
    RelationshipType.MEMBER_OF: "Member of",
    RelationshipType.EMPLOYED_BY: "Employed by",
    RelationshipType.PART_OF: "Part of",
    RelationshipType.SUBSIDIARY_OF: "Subsidiary of",
    RelationshipType.LOCATED_IN: "Located in",
    RelationshipType.COMMUNICATES_WITH: "Communicates with",
    RelationshipType.FAMILY_OF: "Family",
    RelationshipType.ASSOCIATE_OF: "Associate of",
    RelationshipType.APPEARS_IN_PHOTO_WITH: "Appears in photo with",
    RelationshipType.SAME_AS: "Same as",
    RelationshipType.OWNS: "Owns",
}


def relationship_label(relationship_type: RelationshipType) -> str:
    """Human label for a relationship type."""
    return RELATIONSHIP_LABELS.get(relationship_type, relationship_type.value.replace("_", " ").capitalize())


class OntologyRelationship(BaseModel):
    """Wire form of a ``RelationshipSpec`` -- one source of truth for the connection UI."""

    relationship_type: RelationshipType
    label: str
    directed: bool
    symmetric: bool
    allowed_src: list[EntityType]
    allowed_dst: list[EntityType]
    inverse_label: str | None = None
    description: str
    roles: list[str] = Field(default_factory=list, description="Valid attributes['role'] values, if any")


class Ontology(BaseModel):
    """The full entity-layer registry, served so the frontend never hard-codes it."""

    entity_types: list[EntityType]
    selector_types: list[SelectorType]
    selector_subtypes: dict[SelectorType, list[SelectorSubtype]]
    relationships: list[OntologyRelationship]


def build_ontology() -> Ontology:
    """Assemble the ontology registry for the API."""
    relationships = [
        OntologyRelationship(
            relationship_type=rt,
            label=relationship_label(rt),
            directed=spec.directed,
            symmetric=spec.symmetric,
            allowed_src=sorted(spec.allowed_src),
            allowed_dst=sorted(spec.allowed_dst),
            inverse_label=spec.inverse_label,
            description=spec.description,
            roles=[r.value for r in RELATIONSHIP_ROLE_ENUM[rt]] if rt in RELATIONSHIP_ROLE_ENUM else [],
        )
        for rt, spec in RELATIONSHIPS.items()
    ]
    subtypes: dict[SelectorType, list[SelectorSubtype]] = {typ: sorted(subs) for typ, subs in SELECTOR_SUBTYPES.items()}
    return Ontology(
        entity_types=list(EntityType),
        selector_types=list(SelectorType),
        selector_subtypes=subtypes,
        relationships=relationships,
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
