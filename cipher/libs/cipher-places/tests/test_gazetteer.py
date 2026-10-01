"""Resolution rules against a tiny hand-built index (no data file needed)."""

from collections import defaultdict

import pytest

from cipher.places import Gazetteer, Place, PlaceKind, place_key
from cipher.places.gazetteer import place_code

C, A, T = PlaceKind.COUNTRY, PlaceKind.ADMIN1, PlaceKind.CITY
_PLACES = [
    # (id, name, kind, cc, admin1, pop, names, codes)
    ("de", "Germany", C, "DE", None, 83_000_000, ["Germany", "Deutschland"], ["DE"]),
    ("ca", "Canada", C, "CA", None, 38_000_000, ["Canada"], ["CA"]),
    ("us", "United States of America", C, "US", None, 328_000_000, ["United States"], ["US", "USA"]),
    ("ge", "Georgia", C, "GE", None, 3_700_000, ["Georgia"], ["GE"]),
    ("fr", "France", C, "FR", None, 67_000_000, ["France"], ["FR"]),
    ("au", "Australia", C, "AU", None, 26_000_000, ["Australia"], ["AU"]),
    ("mx", "Mexico", C, "MX", None, 127_000_000, ["Mexico"], ["MX"]),
    ("us-de", "Delaware", A, "US", "DE", 0, ["Delaware"], ["DE"]),
    ("us-ca", "California", A, "US", "CA", 0, ["California"], ["CA"]),
    ("us-tx", "Texas", A, "US", "TX", 0, ["Texas"], ["TX"]),
    ("us-ga", "Georgia", A, "US", "GA", 0, ["Georgia"], ["GA"]),
    ("us-wa", "Washington", A, "US", "WA", 0, ["Washington"], ["WA"]),
    ("us-dc", "District of Columbia", A, "US", "DC", 0, ["District of Columbia"], ["DC"]),
    ("us-ak", "Alaska", A, "US", "AK", 0, ["Alaska"], ["AK"]),
    ("mx-15", "México", A, "MX", "15", 0, ["Mexico"], []),
    ("wil-de", "Wilmington", T, "US", "DE", 70_898, ["Wilmington"], []),
    ("wil-nc", "Wilmington", T, "US", "NC", 115_933, ["Wilmington"], []),
    ("paris-fr", "Paris", T, "FR", "11", 2_138_551, ["Paris"], []),
    ("paris-tx", "Paris", T, "US", "TX", 24_782, ["Paris"], []),
    ("dc", "Washington", T, "US", "DC", 689_545, ["Washington"], []),
    ("pekin-il", "Pekin", T, "US", "IL", 32_000, ["Pekin"], []),
    ("moscow", "Moscow", T, "RU", "48", 10_381_222, ["Moscow", "Москва"], []),
    ("nizhniy", "Nizhniy Novgorod", T, "RU", "51", 1_250_000, ["Нижний Новгород"], []),
    ("kyiv", "Kyiv", T, "UA", "12", 2_797_553, ["Kyiv", "Київ"], []),
    ("baghdad", "Baghdad", T, "IQ", "07", 7_216_000, ["Baghdad", "بغداد"], []),
    ("tehran", "Tehran", T, "IR", "26", 7_153_309, ["Tehran", "تهران"], []),
    ("pskov", "Pskov", T, "RU", "60", 201_990, ["Pskov"], []),
]
_ALTERNATES = {"beijing": ("Beijing", "CN", "22", 18_960_744, ["Pékin"])}
_ADMIN_NAMES = {
    "ru-psk": ("Pskov", "RU", "60", ["Pskov", "Псковская область"]),
    "cn-gd": ("Guangdong", "CN", "30", ["广东省"]),
    "iq-anbar": ("Al-Anbar", "IQ", "01", ["محافظة الأنبار"]),
}


@pytest.fixture(scope="module")
def gaz() -> Gazetteer:
    """Index `_PLACES` the way `build` does."""
    places, tables = [], defaultdict(lambda: defaultdict(list))

    def add(table: str, names: list[str], **place) -> None:
        places.append(Place(latitude=0, longitude=0, **place))
        for n in names:
            tables[table][place_key(n)].append(len(places) - 1)
            if (exact := place_key(n, fold_accents=False)) != place_key(n):
                tables[f"exact_{table}"][exact].append(len(places) - 1)

    for pid, name, kind, cc, a1, pop, names, codes in _PLACES:
        add("names", names, id=pid, name=name, kind=kind, country_code=cc, admin1_code=a1, population=pop)
        for c in codes:
            tables["codes"][c].append(len(places) - 1)
    for pid, (name, cc, a1, pop, names) in _ALTERNATES.items():
        add("alt_names", names, id=pid, name=name, kind=T, country_code=cc, admin1_code=a1, population=pop)
    for pid, (name, cc, a1, names) in _ADMIN_NAMES.items():
        add("admin_names", names, id=pid, name=name, kind=A, country_code=cc, admin1_code=a1)
    return Gazetteer(places=places, tables=tables)


def _id(place: Place | None) -> str | None:
    return place.id if place else None


def test_keys_and_codes():
    """Keys fold case/accents/dots/`the`; codes need upper-case or dots."""
    assert place_key("The United States.") == "united states"
    assert place_key("München") == "munchen"
    assert place_key("China’s") == "china"
    assert place_code("U.S.") == "US"
    assert place_code("de") is None  # lower-case word, not a code
    assert place_code("DEU") == "DEU"


@pytest.mark.parametrize(
    ("surface", "before", "after", "expected"),
    [
        ("DE", "Dover, ", " 19904", "us-de"),  # state in address position
        ("DE", "", " 19807", "us-de"),
        ("DE", "", "", None),  # Germany or Delaware, no context -> abstain
        ("DE", "FR, ", ", AU", "de"),  # list of country codes -> Germany
        ("DE", "TX, ", ", DC", "us-de"),  # list of state codes -> Delaware
        ("DC", "", "", "us-dc"),  # one reading
        ("CA", "AK, AZ, ", ", DE, TX", "us-ca"),  # vote over the whole list, ambiguous codes abstain
        ("CA", "FR, ", ", TX", None),  # mixed list -> abstain
        ("CA", "Mountain View, ", " 94043", "us-ca"),
        ("USA", "", "", "us"),  # a code with no state reading
        ("Deutschland", "", "", "de"),
        ("Georgia", "", "", None),  # country vs foreign state
        ("Mexico", "", "", "mx"),  # country beats its own state
        ("Washington", "", "", None),  # state vs a big city outside it
        ("Washington, DC", "", "", "dc"),  # composite surface narrows to the city
        ("Wilmington", "", "", None),  # no dominant namesake
        ("Wilmington", "", ", DE 19807", "wil-de"),  # trailing qualifier
        ("Paris", "", "", "paris-fr"),  # >= 10x the next namesake
        ("Paris", "", ", TX 75460", "paris-tx"),
        ("Nowhere", "", "", None),
        ("Pékin", "", "", "beijing"),  # as written beats accent-folded
        ("Pekin", "", "", "pekin-il"),
        ("Москве", "", "", "moscow"),  # Russian case form -> lemma
        ("Нижнем Новгороде", "", "", "nizhniy"),  # adjective agreed with its noun
        ("Києві", "", "", "kyiv"),  # Ukrainian vowel alternation
        ("ببغداد", "", "", "baghdad"),  # attached Arabic preposition
        ("في بغداد", "", "", "baghdad"),
        ("تِهران", "", "", "tehran"),  # vowel marks and Persian letter variants
        ("Pskov", "", "", "pskov"),  # bare name is the city
        ("Псковской области", "", "", "ru-psk"),  # full form is the province
        ("广东", "", "", "cn-gd"),  # administrative suffix supplied
        ("الأنبار", "", "", "iq-anbar"),  # province word supplied
    ],
)
def test_resolve(gaz: Gazetteer, surface: str, before: str, after: str, expected: str | None):
    """Each rule resolves or abstains as documented."""
    assert _id(gaz.resolve(surface, before=before, after=after)) == expected
