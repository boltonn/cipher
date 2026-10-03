# cipher-places

Offline multilingual gazetteer for resolving `location` name mentions to one
canonical place (country, state/province, city, or curated region).

Everything it needs is committed under `data/`, so it runs and rebuilds offline:

```
data/places.json.gz          # the built index (what `Gazetteer.load()` reads)
data/src/                    # Natural Earth + GeoNames sources the index is built from
data/custom_places.jsonl     # your own places
cipher-places-build          # rebuild data/places.json.gz from data/src (+ custom); downloads only missing sources
```

```python
from cipher.places import Gazetteer

gaz = Gazetteer.load()  # CIPHER_GAZETTEER_PATH overrides the default path
gaz.resolve("Wilmington", after=", DE 19807")  # Wilmington, Delaware
gaz.resolve("DE", before="Dover, ")  # Delaware (address position)
gaz.resolve("DE", before="FR, ")  # None -- Germany or Delaware?
gaz.resolve("Georgia")  # None -- country or US state?
```

Names are matched in their dictionary form in any indexed language; a name that
matches nothing is retried as its lemma (Russian/Ukrainian case forms, via
`pymorphy3`), without an attached Arabic/Persian prefix, or with a Chinese
`省`/`市` suffix (`variants.py`).

## Adding your own places

```
uv run libs/cipher-places/scripts/add_place.py "North Facility" 49.84 24.03 \
    --alias "Північний об'єкт" --alias "Северный объект" --country UA
uv run libs/cipher-places/scripts/add_place.py --remove "North Facility"
```

The script upserts the entry in `data/custom_places.jsonl`, rebuilds the index and
prints how the name and each alias now resolve. A custom place outranks every
other reading. Each line of the file is one JSON object:

```json
{"name": "North Facility", "latitude": 49.84, "longitude": 24.03, "aliases": ["Північний об'єкт", "Северный объект"], "country_code": "UA"}
```

Sources: Natural Earth 10m admin-0/admin-1 (public domain), GeoNames
`cities15000` (CC-BY 4.0, attribute GeoNames). The resolution rules -- and why
each one abstains rather than guesses -- are in `gazetteer.py`'s module docstring.
