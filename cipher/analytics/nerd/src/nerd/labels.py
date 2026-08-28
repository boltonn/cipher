"""Normalize a token-classification model's tags to the ontology vocabulary.

Standard NER checkpoints emit CoNLL tags (`PER`/`PERSON`, `ORG`, `LOC`/`GPE`)
or the full OntoNotes v5 set (`DATE`, `NORP`, `FAC`, `GPE`, ...). We fold those
to the label strings `cipher.schemas.ontology.NER_LABEL_TO_TYPE` understands;
anything unmapped is passed through lowercased so it is still visible.
"""

_TAG_TO_LABEL = {
    "per": "person",
    "person": "person",
    "org": "organization",
    "organization": "organization",
    "company": "organization",
    "loc": "location",
    "location": "location",
    "gpe": "location",
    "fac": "location",
    "facility": "location",
    "address": "address",
    "norp": "organization",  # nationalities / religious / political groups -- closest actor bucket
}


def normalize_label(raw: str) -> str:
    """Map a raw model tag (with any `B-`/`I-` prefix) to an ontology label string."""
    tag = raw.split("-", 1)[-1].strip().lower()
    return _TAG_TO_LABEL.get(tag, tag)
