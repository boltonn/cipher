"""Resolve a place-name mention to one canonical place -- or to nothing when it's genuinely ambiguous.

Precision over recall: a wrong place is worse than an unresolved mention, so
every rule below abstains rather than guesses.

* Two/three-letter codes (`DE`, `CA`, `UK`, `U.S.`) only count when written as a
  code (upper-case or dotted). A code with one reading resolves (`UK`, `DC`). A
  code that is both a state and a country (`DE` Delaware vs Germany, `CA`
  California vs Canada) resolves by position: a state after `City,` or before a
  ZIP/postal code; in a comma list, whichever kind its unambiguous neighbours are
  (`AK, AZ, CA` -> states; `FR, DE, AU` -> countries; mixed -> abstain);
  otherwise abstains.
* A qualifier after the mention (`Wilmington, DE`, `Paris, France`) narrows a
  city to that state/country.
* Otherwise tiers: curated region > country > admin1 > city. A name shared by a
  country and a foreign state (`Georgia`) is ambiguous; a country beats its own
  same-named state (`Mexico`). GeoNames alternate names (historical/colloquial)
  only count when no official name matches, and the provinces of countries
  whose provinces share their capital's name only when no city matches at all
  (`Pskov` is the city, `Псковская область` the province). A state whose name is also a big
  city resolves to the city only if the city lies inside it (`New York`), else
  abstains (`Washington`). A bare city name resolves to its most populous
  namesake only when that is >= 10x the next (`Paris` yes, `Wilmington` no).
* A name is matched as written before it is matched accent-folded (`Pékin` is
  Beijing, not `Pekin`, Illinois). Only a name that matches nothing is retried
  in its dictionary form (`cipher.places.variants`): `Москве` -> `Москва`.
* A custom place (`custom_places.jsonl`, analyst-curated) outranks everything.
"""

import gzip
import json
import os
import re
import unicodedata
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from cipher.places.variants import name_variants

_DOMINANCE = 10
_BIG_CITY = 500_000
_POSTAL_AFTER = re.compile(r"^\s*,?\s*(?:\d{5}(?:-\d{4})?|[A-Z]\d[A-Z]\s?\d[A-Z]\d)\b")
_CITY_BEFORE = re.compile(r"[^\W\d_]{3,}\.?\s*,\s*$")
_LIST_BEFORE = re.compile(r"(?:\b[A-Z]{2,3}\s*,\s*)+$")
_LIST_AFTER = re.compile(r"^(?:\s*,\s*[A-Z]{2,3}\b)+")
_LIST_CODE = re.compile(r"\b[A-Z]{2,3}\b")
_ARABIC_MARKS = re.compile(r"[\u064b-\u0652\u0670\u0640]")
_ARABIC_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ی": "ي", "ک": "ك", "\u200c": " "})
# Lookup order: (table, accent-folded key?). As written before folded, official
# before alternate, and province-only names (`admin_names`) last of all.
_NAME_TABLES = (
    ("exact_names", False),
    ("exact_alt_names", False),
    ("names", True),
    ("alt_names", True),
    ("exact_admin_names", False),
    ("admin_names", True),
)
_ADDRESS_PART = re.compile(r"[^,\n;|]+")
_ADDRESS_NUMBERING = " \t\r0123456789-–/#."
_SPECIFICITY = {"city": 0, "admin1": 1, "country": 2}
_QUALIFIER_AFTER = re.compile(r"^\s*,\s*([^\W\d_][^,\n|;:()\d]{1,29}?)\s*(?=$|[,\n|;:()]|\d)")


class PlaceKind(StrEnum):
    CUSTOM = "custom"
    COUNTRY = "country"
    ADMIN1 = "admin1"
    CITY = "city"
    REGION = "region"


class Place(BaseModel):
    """One canonical place. Field order is the on-disk row order."""

    id: str = Field(description="Source-qualified id, e.g. `wikidata:Q1393`, `geonames:4145381`")
    name: str
    kind: PlaceKind
    country_code: str | None = Field(default=None, description="ISO 3166-1 alpha-2")
    admin1_code: str | None = Field(default=None, description="GeoNames admin1 code within the country (US: postal)")
    latitude: float
    longitude: float
    population: int = Field(default=0)


def default_data_dir() -> Path:
    """`libs/cipher-places/data/`: the committed index, its sources and `custom_places.jsonl` (works offline)."""
    return Path(__file__).resolve().parents[3] / "data"


def default_gazetteer_path() -> Path:
    """`CIPHER_GAZETTEER_PATH`, else the committed `data/places.json.gz` (built by `cipher-places-build`)."""
    return Path(os.environ.get("CIPHER_GAZETTEER_PATH", default_data_dir() / "places.json.gz")).expanduser()


def place_key(text: str, *, fold_accents: bool = True) -> str:
    """Name lookup key: case/width-folded; dots, dashes, possessive and `the` dropped.

    Arabic-script vowel marks and letter variants (Persian `ی`/`ک`, hamza seats)
    are unified. `fold_accents` also strips Latin accents (`München` -> `munchen`).
    """
    key = re.sub(r"['’]s$", "", unicodedata.normalize("NFKC", text).casefold().replace(".", ""))
    key = _ARABIC_MARKS.sub("", key).translate(_ARABIC_LETTERS)
    stripped = "".join(c for c in unicodedata.normalize("NFKD", key) if not unicodedata.combining(c))
    if fold_accents and stripped.isascii():
        key = stripped
    key = re.sub(r"[\s\-‐–—_/'’]+", " ", key).strip(' ,;:()"')
    return re.sub(r"^the ", "", key)


def place_code(text: str) -> str | None:
    """`DE` / `U.S.` / `USA` -> the code; None unless written as a code (upper-case or dotted, 2-3 letters)."""
    letters = text.replace(".", "").strip()
    if 2 <= len(letters) <= 3 and letters.isalpha() and (letters.isupper() or "." in text):
        return letters.upper()
    return None


class Gazetteer:
    """In-memory alias index over countries, admin1 states/provinces, cities and curated regions."""

    def __init__(self, places: list[Place], tables: dict[str, dict[str, list[int]]]):
        self._places = places
        self._tables = tables

    @classmethod
    def load(cls, path: Path | None = None) -> "Gazetteer":
        """Load the compact index written by `cipher.places.build`."""
        raw = json.loads(gzip.decompress(Path(path or default_gazetteer_path()).read_bytes()))
        fields = list(Place.model_fields)
        places = [Place(**dict(zip(fields, row, strict=True))) for row in raw.pop("places")]
        return cls(places=places, tables=raw)

    def __len__(self) -> int:
        """Number of indexed places."""
        return len(self._places)

    def candidates(self, text: str) -> list[Place]:
        """Every place `text` could name (codes only when written as a code; alternates only if nothing official)."""
        if code := place_code(text):
            ids = self._tables["codes"].get(code) or self._tables["alt_codes"].get(code, [])
            return [self._places[i] for i in ids]
        for name in (text, *name_variants(text)):
            if ids := self._name_ids(name):
                return [self._places[i] for i in ids]
        return []

    def _name_ids(self, name: str) -> list[int]:
        """First table in `_NAME_TABLES` order that knows `name`."""
        keys = {False: place_key(name, fold_accents=False), True: place_key(name)}
        for table, folded in _NAME_TABLES:
            if ids := self._tables.get(table, {}).get(keys[folded]):
                return ids
        return []

    def resolve(self, surface: str, *, before: str = "", after: str = "") -> Place | None:
        """The one place `surface` names given the text immediately `before`/`after` it, or None."""
        if "," in surface:
            head, _, tail = surface.rpartition(",")
            if head.strip() and (scope := self._scope(tail.strip())):
                return self._choose(self._within(self.candidates(head.strip()), scope))

        if place_code(surface):
            return self._resolve_code(self.candidates(surface), before=before, after=after)

        cands = self.candidates(surface)
        if (m := _QUALIFIER_AFTER.match(after)) and (scope := self._scope(m.group(1))):
            cands = self._within(cands, scope) or cands
        return self._choose(cands)

    def place_in_address(self, address: str) -> tuple[Place, int, int] | None:
        """The most specific place a postal address names (city, else state, else country), with its offsets.

        Each comma / line part, stripped of house numbers and postal codes, is resolved in the
        context of the rest (`Philadelphia` before `, PA 19104` -> Philadelphia, US). Street
        lines name no place and an ambiguous name resolves to nothing, so nothing is guessed.
        """
        best: tuple[int, Place, int, int] | None = None
        for part in _ADDRESS_PART.finditer(address):
            core = part.group().strip(_ADDRESS_NUMBERING)
            if len(core) < 2:
                continue
            start = part.start() + part.group().find(core)
            end = start + len(core)
            place = self.resolve(core, before=address[:start], after=address[end:])
            rank = _SPECIFICITY.get(place.kind.value, 3) if place else None
            if place and (best is None or rank < best[0]):
                best = (rank, place, start, end)
        return best[1:] if best else None

    def _resolve_code(self, cands: list[Place], *, before: str, after: str) -> Place | None:
        if len(cands) <= 1:
            return cands[0] if cands else None
        states = [p for p in cands if p.kind is PlaceKind.ADMIN1]
        others = [p for p in cands if p.kind is not PlaceKind.ADMIN1]
        if len(states) != 1 or len(others) != 1:
            return None
        if _POSTAL_AFTER.match(after) or _CITY_BEFORE.search(before):
            return states[0]
        neighbour_kinds = set()
        for m in (_LIST_BEFORE.search(before), _LIST_AFTER.match(after)):
            for code in _LIST_CODE.findall(m.group(0)) if m else ():
                if len(kinds := {p.kind is PlaceKind.ADMIN1 for p in self.candidates(code)}) == 1:
                    neighbour_kinds |= kinds
        if len(neighbour_kinds) == 1:
            return states[0] if neighbour_kinds.pop() else others[0]
        return None

    def _scope(self, text: str) -> Place | None:
        """A trailing qualifier (`DE`, `Delaware`, `France`) as one country or admin1."""
        cands = [p for p in self.candidates(text) if p.kind in (PlaceKind.COUNTRY, PlaceKind.ADMIN1)]
        if place_code(text):
            states = [p for p in cands if p.kind is PlaceKind.ADMIN1]
            if len(states) == 1:
                return states[0]
        return cands[0] if len(cands) == 1 else None

    @staticmethod
    def _within(cands: list[Place], scope: Place) -> list[Place]:
        if scope.kind is PlaceKind.COUNTRY:
            return [p for p in cands if p.country_code == scope.country_code and p.kind is not PlaceKind.COUNTRY]
        return [
            p
            for p in cands
            if p.kind is PlaceKind.CITY and p.country_code == scope.country_code and p.admin1_code == scope.admin1_code
        ]

    @staticmethod
    def _choose(cands: list[Place]) -> Place | None:
        by_kind: dict[PlaceKind, list[Place]] = {kind: [] for kind in PlaceKind}
        for p in {p.id: p for p in cands}.values():
            by_kind[p.kind].append(p)
        regions, countries, states = by_kind[PlaceKind.REGION], by_kind[PlaceKind.COUNTRY], by_kind[PlaceKind.ADMIN1]
        cities = sorted(by_kind[PlaceKind.CITY], key=lambda p: p.population, reverse=True)

        if custom := by_kind[PlaceKind.CUSTOM]:
            return custom[0] if len(custom) == 1 else None
        if regions:
            return regions[0] if len(regions) == 1 else None
        if countries:
            own = len(countries) == 1 and all(s.country_code == countries[0].country_code for s in states)
            return countries[0] if own else None
        if states:
            if len(states) > 1:
                return None
            state = states[0]
            big = [c for c in cities if c.population >= _BIG_CITY]
            if not big:
                return state
            inside = [c for c in big if (c.country_code, c.admin1_code) == (state.country_code, state.admin1_code)]
            return inside[0] if len(inside) == 1 and len(big) == 1 else None
        if cities and (len(cities) == 1 or cities[0].population >= _DOMINANCE * max(cities[1].population, 1)):
            return cities[0]
        return None
