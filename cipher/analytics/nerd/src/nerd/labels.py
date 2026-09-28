"""Normalize a token-classification model's tags to an ontology-resolvable label.

The supervised model this service ships now emits the schema-aligned canonical
tagset directly (``person.name``, ``organization.name``, ``location.name``,
``location.address``) -- those pass straight through and
``cipher.schemas.graph.ontology.mention_target`` maps them to a
``(EntityType, attribute)`` pair.

A legacy / third-party checkpoint that emits CoNLL (``PER``/``ORG``/``LOC``) or
OntoNotes (``GPE``/``FAC``/...) tags still works: those are folded here, and
anything else is passed through lower-cased for ``mention_target``'s own
forgiving alias handling.
"""

_TAG_TO_LABEL = {
    "per": "person.name",
    "pers": "person.name",
    "person": "person.name",
    "org": "organization.name",
    "organization": "organization.name",
    "company": "organization.name",
    "loc": "location.name",
    "location": "location.name",
    "gpe": "location.name",
    "fac": "location.name",
    "facility": "location.name",
    "address": "location.address",
}


def normalize_label(raw: str) -> str:
    """Map a raw model tag (with any ``B-``/``I-`` prefix) to an ontology label string."""
    tag = raw.split("-", 1)[-1].strip().lower()
    if "." in tag:  # already the canonical `<type>.<attribute>` form
        return tag
    return _TAG_TO_LABEL.get(tag, tag)
