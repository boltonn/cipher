"""The field vocabulary (`data/field_types.json`) and the header/role lexicon, loaded once."""

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from importlib.resources import files

from cipher.names import fold
from cipher.schemas.graph.ontology import EntityType, SelectorType
from cipher.schemas.ingestion.table_mapping import OTHER_FIELD


class FieldUse(StrEnum):
    """What a column of this field type becomes at emit time."""

    ENTITY = "entity"  # an attribute (or part of one) of an entity slot
    EDGE_TIME = "edge_time"  # the observed date of the row's edges
    EDGE_ATTRIBUTE = "edge_attribute"  # copied onto the row's edges
    KEY = "key"
    TEXT = "text"  # free text -- a later NER pass over the cell
    IGNORE = "ignore"


@dataclass(frozen=True, slots=True)
class FieldType:
    id: str
    label: str
    description: str
    use: FieldUse
    entity_type: EntityType | None = None
    attribute: str | None = None
    part: str | None = None
    selector_type: str | None = None
    selector_subtype: str | None = None
    needs_ontology: bool = False

    @property
    def group(self) -> str:
        """`person`, `location`, `selector`, `time`, ... (the id's prefix)."""
        return self.id.split(".", 1)[0]

    @property
    def ontology_selector_type(self) -> SelectorType | None:
        """The selector type, when the ontology has it."""
        try:
            return SelectorType(self.selector_type) if self.selector_type else None
        except ValueError:
            return None


def _data(name: str) -> dict | list:
    return json.loads(files("pytabular.data").joinpath(name).read_text(encoding="utf-8"))


@cache
def field_types() -> dict[str, FieldType]:
    """Every field type by id, in vocabulary order."""
    out: dict[str, FieldType] = {}
    for raw in _data("field_types.json"):
        entity_type = raw.get("entity_type")
        out[raw["id"]] = FieldType(
            id=raw["id"],
            label=raw["label"],
            description=raw["description"],
            use=FieldUse(raw["use"]),
            entity_type=EntityType(entity_type) if entity_type else None,
            attribute=raw.get("attribute"),
            part=raw.get("part"),
            selector_type=raw.get("selector_type"),
            selector_subtype=raw.get("selector_subtype"),
            needs_ontology=bool(raw.get("needs_ontology")),
        )
    return out


def field_type(field_id: str) -> FieldType:
    """A field type by id; unknown ids fall back to `other`."""
    return field_types().get(field_id) or field_types()[OTHER_FIELD]


_SPLIT = re.compile(r"[\s_\-./\\:;,()\[\]{}#№*\"'`]+")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


def normalize_header(header: str) -> str:
    """`Sender_PhoneNumber (mobile)` -> `sender phone number mobile`; scripts kept, accents folded."""
    spaced = _CAMEL.sub(" ", header or "")
    return " ".join(t for t in _SPLIT.split(fold(spaced).lower()) if t)


def header_tokens(header: str) -> list[str]:
    """Normalized header split into tokens."""
    return normalize_header(header).split()


def is_spaceless(text: str) -> bool:
    """True for scripts written without spaces (CJK), where synonyms match as substrings."""
    return any("぀" <= ch <= "鿿" or "가" <= ch <= "힯" for ch in text)


STRONG_CUE = 0.19


@cache
def header_synonyms() -> dict[str, tuple[str, ...]]:
    """Field id -> normalized header synonyms.

    Selector fields also take pyselectors' strong context cue words for their type:
    the words that announce a phone or a plate in text name its column too. Weak
    cues (`subscriber` for an IMSI) are left out -- in text they nudge, as a header
    they would decide.
    """
    from pyselectors import cue_words

    raw: dict[str, list[str]] = {fid: list(words) for fid, words in _data("header_lexicon.json")["fields"].items()}
    for spec in field_types().values():
        if spec.ontology_selector_type is not None:
            raw.setdefault(spec.id, []).extend(
                w for words in cue_words(spec.ontology_selector_type, min_weight=STRONG_CUE).values() for w in words
            )
    return {
        fid: tuple(dict.fromkeys(normalize_header(s) for s in synonyms if normalize_header(s)))
        for fid, synonyms in raw.items()
    }


@cache
def role_synonyms() -> dict[str, tuple[str, ...]]:
    """Role name (`sender`, `receiver`, `owner`, ...) -> normalized synonyms."""
    raw = _data("header_lexicon.json")["roles"]
    return {
        role: tuple(dict.fromkeys(normalize_header(s) for s in synonyms if normalize_header(s)))
        for role, synonyms in raw.items()
    }


@cache
def demonyms() -> dict[str, str]:
    """Folded demonym / nationality word -> ISO country code."""
    return {normalize_header(word): code for code, words in _data("demonyms.json").items() for word in words}
