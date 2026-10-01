"""Build the offline gazetteer index: `cipher-places-build [--src DIR] [--out PATH] [--custom PATH]`.

Sources (downloaded into `--src` when missing):

* Natural Earth 10m admin-0 countries + admin-1 states/provinces (public domain):
  label coordinates, ISO/postal codes, names in ~25 languages.
* GeoNames `cities15000` (CC-BY 4.0): every city >= 15k people, with population
  and multilingual alternate names.

Admin-1 is indexed only for countries whose admin-1 units are the well-known
states/provinces people write in text; elsewhere Natural Earth's admin-1 is
fine-grained (France's départements would make "Paris" collide with its city).
`_ADMIN1_ALTERNATE_COUNTRIES` name their provinces after the capital (`Pskov`),
so those are indexed last (`admin_names`): the bare name stays the city, the full
form (`Псковская область`, `محافظة الأنبار`, `广东省`) is the province.

`--custom` (default `custom_places.jsonl` beside the index) adds analyst-curated
places, one JSON object per line -- see `CustomPlace`.
"""

import argparse
import csv
import gzip
import io
import json
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

from cipher.places.gazetteer import Place, PlaceKind, default_gazetteer_path, place_code, place_key

_NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
_SOURCES = {
    "ne_10m_admin_0_countries.geojson": f"{_NE}/ne_10m_admin_0_countries.geojson",
    "ne_10m_admin_1_states_provinces.geojson": f"{_NE}/ne_10m_admin_1_states_provinces.geojson",
    "cities15000.zip": "https://download.geonames.org/export/dump/cities15000.zip",
}
_ADMIN1_COUNTRIES = {"US", "CA", "AU", "BR", "IN", "DE", "MX"}
_ADMIN1_ALTERNATE_COUNTRIES = {"RU", "UA", "CN", "IR", "IQ", "SY", "EG", "SA", "ES"}
_ADMIN1_CODE_COUNTRIES = {"US", "CA"}
_GENERIC_NAMES = {"eastern", "western", "northern", "southern", "central", "north", "south", "east", "west", "centre"}
_LANGS = ["ar", "bn", "de", "el", "en", "es", "fa", "fr", "he", "hi", "hu", "id", "it", "ja", "ko", "nl", "pl", "pt", "ru", "sv", "tr", "uk", "ur", "vi", "zh", "zht"]  # fmt: skip

_EXTRA_COUNTRY_NAMES = {"america": "US", "britain": "GB", "great britain": "GB", "holland": "NL", "中国": "CN"}
_EXTRA_COUNTRY_CODES = {"UK": "GB", "UAE": "AE"}
_REGIONS = {
    "europe": (54.5, 15.3),
    "asia": (34.0, 100.6),
    "africa": (8.8, 34.5),
    "north america": (54.5, -105.3),
    "south america": (-8.8, -55.5),
    "latin america": (-14.2, -60.0),
    "central america": (12.8, -85.6),
    "middle east": (29.3, 42.5),
    "oceania": (-22.7, 140.0),
    "antarctica": (-82.9, 135.0),
    "caribbean": (15.0, -75.0),
    "scandinavia": (64.0, 15.0),
    "silicon valley": (37.39, -122.06),
    "bay area": (37.8, -122.3),
    "new england": (43.97, -71.5),
    "midwest": (41.5, -89.5),
    "england": (52.36, -1.17),
    "scotland": (56.49, -4.2),
    "wales": (52.13, -3.78),
    "northern ireland": (54.79, -6.49),
}


class _Index:
    """Alias tables, keeping official names/codes apart from GeoNames alternates.

    Alternates include historical and colloquial names ("Philadelphia" for
    Amman), so lookups use them only when nothing official matches.
    """

    def __init__(self):
        self.places: list[Place] = []
        self.tables: dict[str, dict[str, set[int]]] = {
            t: defaultdict(set)
            for t in ("names", "codes", "alt_names", "alt_codes", "admin_names")
        }
        self.tables |= {f"exact_{t}": defaultdict(set) for t in ("names", "alt_names", "admin_names")}

    def add(
        self,
        place: Place,
        names: list[str | None],
        codes: list[str | None] = (),
        *,
        alternates: list[str] = (),
        admin_names: list[str | None] = (),
    ) -> int:
        idx = len(self.places)
        self.places.append(place)
        for table, values in (("names", names), ("alt_names", alternates), ("admin_names", admin_names)):
            for name in filter(None, values):
                if (key := place_key(name)) and (len(key.replace(" ", "")) > 3 or not key.isascii()):
                    self.tables[table][key].add(idx)
                    if (exact := place_key(name, fold_accents=False)) != key:
                        self.tables[f"exact_{table}"][exact].add(idx)
        for table, values in (("codes", codes), ("alt_codes", [a for a in alternates if a.isupper()])):
            for code in filter(None, values):
                if (c := place_code(code)) or (c := place_code(code.upper())):
                    self.tables[table][c].add(idx)
        return idx

    def dump(self) -> dict:
        fields = list(Place.model_fields)
        return {
            "places": [[p.model_dump(mode="json")[f] for f in fields] for p in self.places],
            **{t: {k: sorted(v) for k, v in rows.items()} for t, rows in self.tables.items()},
        }


def _features(path: Path) -> list[dict]:
    return [f["properties"] for f in json.loads(path.read_text())["features"]]


def _add_countries(index: _Index, path: Path) -> dict[str, int]:
    by_cc: dict[str, int] = {}
    for p in _features(path):
        cc = p["ISO_A2_EH"] if p["ISO_A2_EH"] != "-99" else None
        place = Place(
            id=f"wikidata:{p['WIKIDATAID']}" if p.get("WIKIDATAID") else f"ne:{p['ADM0_A3']}",
            name=p["NAME"],
            kind=PlaceKind.COUNTRY,
            country_code=cc,
            latitude=p["LABEL_Y"],
            longitude=p["LABEL_X"],
            population=int(p.get("POP_EST") or 0),
        )
        names = [p[k] for k in ("NAME", "NAME_LONG", "ADMIN", "FORMAL_EN", "GEOUNIT", "BRK_NAME", "NAME_CIAWF")]
        names += [p.get(f"NAME_{lang.upper()}") for lang in _LANGS]
        codes = [cc, p.get("ABBREV")]  # no ISO alpha-3: collides with airport codes (PHL, LAX)
        idx = index.add(place, names, codes)
        if cc:
            by_cc[cc] = idx
    for name, cc in _EXTRA_COUNTRY_NAMES.items():
        index.tables["names"][place_key(name)].add(by_cc[cc])
    for code, cc in _EXTRA_COUNTRY_CODES.items():
        index.tables["codes"][code].add(by_cc[cc])
    return by_cc


def _add_admin1(index: _Index, path: Path) -> None:
    for p in _features(path):
        cc = p.get("iso_a2")
        if cc not in _ADMIN1_COUNTRIES | _ADMIN1_ALTERNATE_COUNTRIES or not p.get("name") or not (p.get("gn_a1_code") or "").partition(".")[2]:
            continue
        place = Place(
            id=f"wikidata:{p['wikidataid']}" if p.get("wikidataid") else f"ne:{p['adm1_code']}",
            name=p["name"],
            kind=PlaceKind.ADMIN1,
            country_code=cc,
            admin1_code=p["gn_a1_code"].split(".", 1)[1],
            latitude=p["latitude"],
            longitude=p["longitude"],
        )
        alts = (p.get("name_alt") or "").split("|")
        names = [p["name"], p.get("name_en"), p.get("gn_name"), p.get("woe_name"), *alts]
        names += [p.get(f"name_{lang}") for lang in _LANGS]
        codes = [p.get("postal"), *alts] if cc in _ADMIN1_CODE_COUNTRIES else []
        if cc in _ADMIN1_ALTERNATE_COUNTRIES:
            index.add(place, [], admin_names=[n for n in names if n and place_key(n) not in _GENERIC_NAMES])
        else:
            index.add(place, names, codes)


def _add_cities(index: _Index, path: Path) -> None:
    with zipfile.ZipFile(path) as zf, zf.open("cities15000.txt") as fh:
        for row in csv.reader(io.TextIOWrapper(fh, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            alternates = [a for a in row[3].split(",") if a and not any(ch.isdigit() for ch in a) and len(a) < 60]
            place = Place(
                id=f"geonames:{row[0]}",
                name=row[1],
                kind=PlaceKind.CITY,
                country_code=row[8],
                admin1_code=row[10] or None,
                latitude=float(row[4]),
                longitude=float(row[5]),
                population=int(row[14] or 0),
            )
            index.add(place, [row[1], row[2]], alternates=alternates)


def _add_regions(index: _Index) -> None:
    for name, (lat, lon) in _REGIONS.items():
        place = Place(
            id=f"cipher:region:{name.replace(' ', '-')}", name=name.title(), kind=PlaceKind.REGION,
            latitude=lat, longitude=lon,
        )  # fmt: skip
        index.add(place, [name])


class CustomPlace(BaseModel):
    """One line of `custom_places.jsonl`: a place the public sources lack (a facility, a district, a local name)."""

    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    aliases: list[str] = Field(default_factory=list, description="Other spellings, in any language or script")
    country_code: str | None = Field(default=None, description="ISO 3166-1 alpha-2")


def _add_custom(index: _Index, path: Path) -> None:
    for line in filter(str.strip, path.read_text().splitlines()):
        custom = CustomPlace.model_validate_json(line)
        place = Place(
            id=f"custom:{place_key(custom.name).replace(' ', '-')}", name=custom.name, kind=PlaceKind.CUSTOM,
            country_code=custom.country_code, latitude=custom.latitude, longitude=custom.longitude,
        )  # fmt: skip
        index.add(place, [custom.name, *custom.aliases])


def build(src: Path, out: Path, custom: Path | None = None) -> int:
    """Download any missing sources into `src` and write the gzipped index to `out`. Returns place count."""
    src.mkdir(parents=True, exist_ok=True)
    for name, url in _SOURCES.items():
        if not (src / name).exists():
            urllib.request.urlretrieve(url, src / name)

    index = _Index()
    _add_countries(index, src / "ne_10m_admin_0_countries.geojson")
    _add_admin1(index, src / "ne_10m_admin_1_states_provinces.geojson")
    _add_cities(index, src / "cities15000.zip")
    _add_regions(index)
    if custom is not None and custom.exists():
        _add_custom(index, custom)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(gzip.compress(json.dumps(index.dump(), ensure_ascii=False, separators=(",", ":")).encode()))
    return len(index.places)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, default=default_gazetteer_path().parent / "src")
    parser.add_argument("--out", type=Path, default=default_gazetteer_path())
    parser.add_argument("--custom", type=Path, default=default_gazetteer_path().parent / "custom_places.jsonl")
    args = parser.parse_args()
    count = build(args.src, args.out, args.custom)
    print(f"wrote {count} places -> {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
