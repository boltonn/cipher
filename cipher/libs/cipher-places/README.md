# cipher-places

Offline multilingual gazetteer for resolving `location` name mentions to one
canonical place (country, state/province, city, or curated region).

```
cipher-places-build            # downloads sources, writes ~/models/gazetteer/places.json.gz
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

Put one JSON object per line in `~/models/gazetteer/custom_places.jsonl` and
re-run `cipher-places-build`. A custom place outranks every other reading.

```json
{"name": "North Facility", "latitude": 49.84, "longitude": 24.03, "aliases": ["Північний об'єкт", "Северный объект"], "country_code": "UA"}
```

Sources: Natural Earth 10m admin-0/admin-1 (public domain), GeoNames
`cities15000` (CC-BY 4.0, attribute GeoNames). The resolution rules -- and why
each one abstains rather than guesses -- are in `gazetteer.py`'s module docstring.
