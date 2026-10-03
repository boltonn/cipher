"""Add (or replace) a custom place, rebuild the gazetteer offline, and show how it resolves.

    uv run libs/cipher-places/scripts/add_place.py "North Facility" 49.84 24.03 \\
        --alias "Північний об'єкт" --alias "Северный объект" --country UA
    uv run libs/cipher-places/scripts/add_place.py --remove "North Facility"

Entries live in `data/custom_places.jsonl` (one per name, matched like the gazetteer matches names);
a custom place outranks every public reading of the same name.
"""

import argparse
from pathlib import Path

from cipher.places import Gazetteer, default_data_dir, default_gazetteer_path, place_key
from cipher.places.build import CustomPlace, build


def _read(path: Path) -> list[CustomPlace]:
    if not path.exists():
        return []
    return [CustomPlace.model_validate_json(line) for line in filter(str.strip, path.read_text().splitlines())]


def _write(path: Path, places: list[CustomPlace]) -> None:
    path.write_text("".join(f"{p.model_dump_json(exclude_defaults=True)}\n" for p in places))


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", nargs="?", help="Canonical name")
    parser.add_argument("latitude", nargs="?", type=float)
    parser.add_argument("longitude", nargs="?", type=float)
    parser.add_argument("--alias", action="append", default=[], help="Another spelling (repeatable, any script)")
    parser.add_argument("--country", default=None, help="ISO 3166-1 alpha-2 code, e.g. UA")
    parser.add_argument("--remove", metavar="NAME", help="Delete the custom place with this name instead")
    args = parser.parse_args()

    custom_path = default_data_dir() / "custom_places.jsonl"
    name = args.remove or args.name
    if name is None or (not args.remove and (args.latitude is None or args.longitude is None)):
        parser.error("give NAME LATITUDE LONGITUDE, or --remove NAME")

    places = [p for p in _read(custom_path) if place_key(p.name) != place_key(name)]
    if args.remove:
        print(f"removed {name!r}" if len(places) < len(_read(custom_path)) else f"no custom place named {name!r}")
    else:
        country_code = args.country.upper() if args.country else None
        places.append(
            CustomPlace(
                name=name, latitude=args.latitude, longitude=args.longitude, aliases=args.alias, country_code=country_code
            )
        )
    _write(custom_path, places)

    count = build(src=default_data_dir() / "src", out=default_gazetteer_path(), custom=custom_path)
    print(f"rebuilt gazetteer: {count} places, {len(places)} custom")
    if not args.remove:
        gazetteer = Gazetteer.load()
        for surface in (name, *args.alias):
            place = gazetteer.resolve(surface)
            print(f"  {surface!r} -> {place.name if place else None} ({place.id if place else 'unresolved'})")


if __name__ == "__main__":
    main()
