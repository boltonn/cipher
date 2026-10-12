"""Value detector: the share of sampled cells that validate as each field type.

Most field types have a per-cell check (`cell_check`), so the same code scores a
column and, once a user has picked a type, reports its hit rate and failing cells.
Selectors and coordinates use pyselectors' whole-cell validation
(`resolve_cell`, `parse_degrees`, `parse_coordinate_cell`); places use the offline
gazetteer; names use cipher-names signals. Nothing selector-shaped is matched here.
"""

import re
import statistics
from collections.abc import Callable
from datetime import datetime
from functools import cache, lru_cache

from cipher.names import canonical_forms, dominant_script
from cipher.places import Gazetteer, PlaceKind
from cipher.places.gazetteer import place_code
from cipher.schemas.graph.ontology import EntityType, SelectorType, guess_actor_type
from pytabular.detectors import ColumnScores, TableContext
from pytabular.fields import demonyms, normalize_header
from pytabular.profile import ColumnSample, is_number

MAX_VALUES = 300
PROBE_VALUES = 30

_DATE = re.compile(
    r"^(?P<a>\d{1,4})[-./年](?P<b>\d{1,2})[-./月](?P<c>\d{1,4})日?"
    r"(?:[ T](?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2})(?:[.,]\d+)?)?\s*(?:Z|[AP]M|[+-]\d{2}:?\d{2})?)?$",
    re.IGNORECASE,
)
_MONTH_DATE = re.compile(
    r"^\d{1,2}[ -](jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?[ -]\d{2,4}", re.IGNORECASE
)
_TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_DECIMAL = re.compile(r"^[-+]?\d{1,3}\.\d+$")
_INT = re.compile(r"^[-+]?\d+$")
_PLAIN_DECIMAL = re.compile(r"^[-+]?\d+[.,]\d+$")
_REFERENCE = re.compile(r"^[A-Z]{0,5}[-_/]?\d{5,}[-_/]?[A-Z\d]*$", re.IGNORECASE)
_UUID = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$", re.IGNORECASE)
_POSTAL = re.compile(
    r"^(\d{5}(-\d{4})?|\d{6}|\d{3}-\d{4}|\d{4}|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}|[A-Z]\d[A-Z] ?\d[A-Z]\d)$"
)
_NAME_TOKEN = re.compile(r"^[^\W\d_][^\W\d_'’.\-]*[.]?$")
_PATRONYMIC = re.compile(r"(ович|евич|ьич|ична|овна|евна|инична|ovich|evich|ovna|evna|ichna)$", re.IGNORECASE)
_SURNAME = re.compile(
    r"(ов|ев|ёв|ин|ын|ова|ева|ина|ына|ский|ская|цкий|цкая|енко|ук|юк|ян|дзе|швили|ov|ev|ova|eva|in|ina|sky|skaya|enko|uk|yan|ian|zadeh|zade|pour|son|sen|ez|ini)$",
    re.IGNORECASE,
)
_LEGAL_FORM = re.compile(
    r"\b(ооо|оао|зао|пао|ао|ип|нко|фгуп|муп|тов|прат|пп|llc|inc|ltd|llp|plc|corp|co|gmbh|ag|sa|sas|sarl|srl|bv|nv|oy|ab|as|pjsc|jsc|"
    r"corporation|incorporated|limited|bank|банк|group|holding|холдинг|university|университет|ministry|министерство|company|компания)\b|有限公司|公司|集团|银行|شركة|شرکت|بانک|مؤسسة",
    re.IGNORECASE,
)
_STREET = re.compile(
    r"\b(ул|улица|пр|проспект|пер|переулок|ш|шоссе|д|дом|кв|корп|стр|бул|наб|пл|вул|street|st|avenue|ave|road|rd|blvd|lane|ln|drive|dr|"
    r"rue|av|calle|carrera|via|strasse|str)\b\.?|路|街|号|弄|خیابان|کوچه|پلاک|شارع",
    re.IGNORECASE,
)
_GENDER = frozenset(
    [
        "m",
        "f",
        "male",
        "female",
        "man",
        "woman",
        "м",
        "ж",
        "муж",
        "жен",
        "мужской",
        "женский",
        "мужчина",
        "женщина",
        "ч",
        "чол",
        "жін",
        "男",
        "女",
        "ذكر",
        "أنثى",
        "مرد",
        "زن",
        "h",
        "homme",
        "femme",
        "hombre",
        "mujer",
    ]
)
_BOOLEAN = frozenset(
    [
        "true",
        "false",
        "yes",
        "no",
        "y",
        "n",
        "да",
        "нет",
        "так",
        "ні",
        "是",
        "否",
        "نعم",
        "لا",
        "بله",
        "خیر",
        "oui",
        "non",
        "sí",
        "si",
        "0",
        "1",
    ]
)
_DIRECTION = frozenset(
    [
        "in",
        "out",
        "incoming",
        "outgoing",
        "inbound",
        "outbound",
        "sent",
        "received",
        "mo",
        "mt",
        "debit",
        "credit",
        "dr",
        "cr",
        "вх",
        "исх",
        "входящий",
        "исходящий",
        "входящая",
        "исходящая",
        "приход",
        "расход",
        "вхідний",
        "вихідний",
        "呼入",
        "呼出",
        "主叫",
        "被叫",
        "收入",
        "支出",
        "وارد",
        "صادر",
        "ورودی",
        "خروجی",
        "entrant",
        "sortant",
        "entrante",
        "saliente",
    ]
)
_CURRENCY = frozenset(
    [
        "usd",
        "eur",
        "rub",
        "rur",
        "gbp",
        "cny",
        "rmb",
        "jpy",
        "chf",
        "cad",
        "aud",
        "uah",
        "byn",
        "kzt",
        "try",
        "irr",
        "aed",
        "sar",
        "inr",
        "krw",
        "hkd",
        "sgd",
        "brl",
        "mxn",
        "pln",
        "czk",
        "sek",
        "nok",
        "dkk",
        "ils",
        "egp",
        "usdt",
        "btc",
        "eth",
        "$",
        "€",
        "£",
        "¥",
        "₽",
        "₴",
        "₸",
        "₺",
        "﷼",
        "руб",
        "р.",
        "доллар",
        "евро",
        "元",
        "人民币",
    ]
)

_SELECTOR_FIELDS: dict[str, SelectorType] = {
    "selector.phone": SelectorType.PHONE,
    "selector.email": SelectorType.EMAIL,
    "selector.ip": SelectorType.IP,
    "selector.iban": SelectorType.IBAN,
    "selector.bank_card": SelectorType.BANK_CARD,
    "selector.imei": SelectorType.IMEI,
    "selector.imsi": SelectorType.IMSI,
    "selector.domain": SelectorType.DOMAIN,
    "selector.national_id": SelectorType.NATIONAL_ID,
    "selector.crypto_address": SelectorType.CRYPTO_ADDRESS,
    "selector.social_handle": SelectorType.SOCIAL_HANDLE,
    "selector.passport": SelectorType.PASSPORT,
    "selector.license_plate": SelectorType.LICENSE_PLATE,
    "selector.mac_address": SelectorType.MAC_ADDRESS,
    "organization.tax_id": SelectorType.NATIONAL_ID,
}
_SCRIPT_REGION = {"cyrillic": "RU", "han": "CN", "arabic": "IR", "hangul": "KR", "kana": "JP"}


@cache
def gazetteer() -> Gazetteer:
    """The offline gazetteer, loaded once."""
    return Gazetteer.load()


PHONE_REGIONS = ("US", "GB", "FR", "DE", "ES", "IT", "RU", "UA", "CN", "IR", "EG", "TR", "IN")


@lru_cache(maxsize=200_000)
def _selector_ok(value: str, selector_type: SelectorType, region: str | None) -> bool:
    from pyselectors import resolve_cell

    return resolve_cell(value, selector_type, region=region) is not None


@lru_cache(maxsize=100_000)
def _degrees(value: str) -> tuple[float, str | None] | None:
    from pyselectors import parse_degrees

    text = value.strip()
    parsed = parse_degrees(text)
    # A bare integer is a count, not a coordinate: need a decimal part or a hemisphere / degree sign.
    if parsed is None or (parsed[1] is None and not any(ch in text for ch in ".,°")):
        return None
    return parsed


@lru_cache(maxsize=100_000)
def _place_kinds(value: str) -> frozenset[PlaceKind]:
    if len(value) > 60 or any(ch.isdigit() for ch in value):
        return frozenset()
    return frozenset(p.kind for p in gazetteer().candidates(value))


def parse_date(value: str) -> tuple[datetime | None, bool]:
    """A date in any common numeric order (Y-M-D, D.M.Y, M/D/Y, 2024年1月5日) or `5 Jan 2024`; also whether it has a time."""
    text = value.strip()
    if _MONTH_DATE.match(text):
        for fmt in ("%d %b %Y", "%d-%b-%Y", "%d %B %Y", "%d-%b-%y"):
            try:
                return datetime.strptime(text[:11].strip(), fmt), False
            except ValueError:
                continue
        return None, False
    match = _DATE.match(text)
    if not match:
        return None, False
    a, b, c = (int(match[k]) for k in ("a", "b", "c"))
    if len(match["a"]) == 4:
        year, month, day = a, b, c
    elif len(match["c"]) in (2, 4):
        year = c if len(match["c"]) == 4 else 2000 + c if c < 50 else 1900 + c
        day, month = (b, a) if b > 12 >= a else (a, b)
    else:
        return None, False
    try:
        parsed = datetime(year, month, day, int(match["h"] or 0), int(match["mi"] or 0), int(match["s"] or 0))
    except ValueError:
        return None, False
    return (parsed, match["h"] is not None) if 1850 <= year <= 2100 else (None, False)


def parse_float(value: str) -> float | None:
    """`1 234,5` -> 1234.5; None when not a number."""
    try:
        return float(value.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def _is_name_like(value: str) -> bool:
    tokens = value.replace(",", " ").split()
    return 1 <= len(tokens) <= 5 and all(_NAME_TOKEN.match(t) for t in tokens) and len(value) <= 60


def _is_spaceless_name(value: str) -> bool:
    """`王伟` / `김민준`: 2-4 Han or Hangul characters, surname first, no spaces."""
    return 2 <= len(value) <= 4 and all("\u4e00" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af" for ch in value)


def _is_full_name(value: str) -> bool:
    if _is_spaceless_name(value):
        return True
    return _is_name_like(value) and len(value.split()) >= 2 and not _is_org(value)


def _is_known_given(value: str) -> bool:
    return len(canonical_forms(value)) > 1


def _is_org(value: str) -> bool:
    letters = sum(ch.isalpha() for ch in value)
    if letters < 0.6 * len(value.replace(" ", "")) or "@" in value or _is_address(value):
        return False
    if _LEGAL_FORM.search(value):
        return True
    if any(ch.isdigit() for ch in value):
        return False
    # Registries often write people in capitals, which `guess_actor_type` reads as an acronym.
    return not value.isupper() and guess_actor_type(value) is EntityType.ORGANIZATION


def _is_address(value: str) -> bool:
    return (
        len(value) >= 8 and (bool(_STREET.search(value)) or value.count(",") >= 2) and any(ch.isdigit() for ch in value)
    )


def _is_epoch(value: str) -> bool:
    if not _INT.match(value):
        return False
    number = int(value)
    return 946_684_800 <= number <= 2_100_000_000 or 946_684_800_000 <= number <= 2_100_000_000_000


def _is_latitude(value: str) -> bool:
    parsed = _degrees(value)
    return parsed is not None and parsed[1] in (None, "lat") and -90 <= parsed[0] <= 90


def _is_longitude(value: str) -> bool:
    parsed = _degrees(value)
    return parsed is not None and parsed[1] in (None, "lon") and -180 <= parsed[0] <= 180


def _is_pair(value: str) -> bool:
    from pyselectors import parse_coordinate_cell

    return parse_coordinate_cell(value) is not None


def _is_age(value: str) -> bool:
    return bool(_INT.match(value)) and 0 <= int(value) <= 120


def _is_amount(value: str) -> bool:
    stripped = value.strip("$€£¥₽ ").replace("\u00a0", "")
    return is_number(stripped) or bool(re.match(r"^[$€£¥₽]\s?\d", value))


@cache
def cell_checks(region: str | None) -> dict[str, Callable[[str], bool]]:
    """Per-cell validators by field id (fields without one are scored by header or model only)."""
    checks: dict[str, Callable[[str], bool]] = {
        field_id: (lambda v, t=selector_type: _selector_ok(v, t, region))
        for field_id, selector_type in _SELECTOR_FIELDS.items()
    }
    checks["selector.phone"] = lambda v: not _PLAIN_DECIMAL.match(v) and _selector_ok(v, SelectorType.PHONE, region)
    checks["person.full_name"] = _is_full_name
    checks["person.given_name"] = lambda v: _is_name_like(v) and len(v.split()) == 1
    checks["person.surname"] = lambda v: _is_name_like(v) and len(v.split()) == 1
    checks["person.patronymic"] = lambda v: _PATRONYMIC.search(v) is not None and len(v.split()) == 1
    checks["person.date_of_birth"] = lambda v: (
        (d := parse_date(v)[0]) is not None and d.year <= datetime.now().year - 10
    )
    checks["person.age"] = _is_age
    checks["person.gender"] = lambda v: normalize_header(v) in _GENDER
    checks["person.nationality"] = lambda v: (
        normalize_header(v) in demonyms() or (place_code(v) is None and PlaceKind.COUNTRY in _place_kinds(v))
    )
    checks["organization.name"] = _is_org
    checks["location.address"] = _is_address
    checks["location.street"] = lambda v: bool(_STREET.search(v))
    checks["location.postal_code"] = lambda v: _POSTAL.match(v.upper()) is not None
    checks["location.city"] = lambda v: PlaceKind.CITY in _place_kinds(v)
    checks["location.admin_area"] = lambda v: PlaceKind.ADMIN1 in _place_kinds(v)
    checks["location.country"] = lambda v: place_code(v) is None and PlaceKind.COUNTRY in _place_kinds(v)
    checks["location.country_code"] = lambda v: place_code(v) is not None and PlaceKind.COUNTRY in _place_kinds(v)
    checks["location.latitude"] = _is_latitude
    checks["location.longitude"] = _is_longitude
    checks["location.coordinate"] = _is_pair
    checks["time.date"] = lambda v: (r := parse_date(v))[0] is not None and not r[1]
    checks["time.datetime"] = lambda v: (r := parse_date(v))[0] is not None and r[1]
    checks["time.epoch"] = _is_epoch
    checks["time.time"] = lambda v: _TIME.match(v) is not None and int(v.split(":")[0]) < 24
    checks["time.duration"] = lambda v: _TIME.match(v) is not None or (_INT.match(v) is not None and int(v) < 86_400)
    checks["edge.amount"] = _is_amount
    checks["edge.currency"] = lambda v: v.strip().lower() in _CURRENCY
    checks["edge.direction"] = lambda v: normalize_header(v) in _DIRECTION
    checks["edge.count"] = lambda v: _INT.match(v) is not None and 0 <= int(v) < 100_000
    checks["key.row_id"] = lambda v: _INT.match(v) is not None or _UUID.match(v) is not None
    checks["key.reference"] = lambda v: _REFERENCE.match(v) is not None and any(c.isalpha() for c in v)
    checks["other.boolean"] = lambda v: v.strip().lower() in _BOOLEAN
    return checks


# How much a 100% hit rate is worth: strong validators (checksums, strict syntax) near 1,
# shape-only checks lower, because many unrelated columns pass them.
_STRENGTH: dict[str, float] = {
    "selector.email": 1.0,
    "selector.iban": 1.0,
    "selector.bank_card": 0.9,
    "selector.imei": 0.85,
    "selector.imsi": 0.85,
    "selector.ip": 0.95,
    "selector.crypto_address": 1.0,
    "selector.mac_address": 1.0,
    "selector.phone": 0.85,
    "selector.national_id": 0.9,
    "selector.domain": 0.8,
    "selector.social_handle": 0.85,
    "selector.passport": 0.3,
    "selector.license_plate": 0.3,
    "organization.tax_id": 0.5,
    "person.full_name": 0.7,
    "person.given_name": 0.35,
    "person.surname": 0.35,
    "person.patronymic": 0.9,
    "person.date_of_birth": 0.5,
    "person.age": 0.5,
    "person.gender": 0.95,
    "person.nationality": 0.75,
    "organization.name": 0.75,
    "location.address": 0.85,
    "location.street": 0.5,
    "location.postal_code": 0.25,
    "location.city": 0.7,
    "location.admin_area": 0.6,
    "location.country": 0.85,
    "location.country_code": 0.85,
    "location.latitude": 0.7,
    "location.longitude": 0.7,
    "location.coordinate": 1.0,
    "time.date": 0.8,
    "time.datetime": 0.95,
    "time.epoch": 0.6,
    "time.time": 0.8,
    "time.duration": 0.4,
    "edge.amount": 0.5,
    "edge.currency": 0.9,
    "edge.direction": 0.9,
    "edge.count": 0.2,
    "key.row_id": 0.2,
    "key.reference": 0.3,
    "other.boolean": 0.85,
}
DISPROVABLE = frozenset(
    {
        "selector.email",
        "selector.ip",
        "selector.iban",
        "selector.bank_card",
        "selector.imei",
        "selector.imsi",
        "selector.crypto_address",
        "selector.mac_address",
        "location.latitude",
        "location.longitude",
        "location.coordinate",
        "time.date",
        "time.datetime",
        "time.epoch",
        "person.date_of_birth",
    }
)
"""Fields whose validator is reliable enough that a column of failing cells contradicts a header claim."""
_NUMERIC_ONLY = {
    "selector.phone",
    "selector.bank_card",
    "selector.imei",
    "selector.imsi",
    "selector.national_id",
    "organization.tax_id",
}


def best_phone_region(values: list[str], *, region: str | None) -> str | None:
    """The region under which most of a column's numbers validate as phones (the given one wins ties)."""
    sample = values[:40]
    if not sample or region:
        return region
    phone_shaped = sum(1 for v in sample if 7 <= sum(ch.isdigit() for ch in v) <= 15)
    if phone_shaped < 0.5 * len(sample):
        return None
    rates = {r: sum(1 for v in sample if _selector_ok(v, SelectorType.PHONE, r)) for r in (None, *PHONE_REGIONS)}
    best = max(rates, key=lambda r: rates[r])
    return best if rates[best] > rates[None] else None


def region_hint(columns: list[ColumnSample], context: TableContext) -> str | None:
    """The user's region, else one implied by the table's dominant script."""
    if context.region:
        return context.region
    text = " ".join(v for c in columns for v in c.values[:20])
    return _SCRIPT_REGION.get(dominant_script(text).value)


def hit_rate(field_id: str, values: list[str], *, region: str | None) -> tuple[float | None, list[str]]:
    """Share of `values` passing `field_id`'s cell check, plus a few failing cells; `None` without a check."""
    check = cell_checks(region).get(field_id)
    if check is None or not values:
        return None, []
    sample = list(dict.fromkeys(values))[:MAX_VALUES]
    failing = [v for v in sample if not check(v)]
    return 1 - len(failing) / len(sample), failing[:5]


class ValidatorDetector:
    name = "validators"

    def score(self, columns: list[ColumnSample], *, context: TableContext) -> list[ColumnScores]:
        """Hit rate × strength per field, with column-level adjustments (distinctness, spread, pairing)."""
        region = region_hint(columns, context)
        checks = cell_checks(region)
        return [self._score_column(column, checks, region) for column in columns]

    def _score_column(
        self, column: ColumnSample, checks: dict[str, Callable[[str], bool]], region: str | None
    ) -> ColumnScores:
        values = list(dict.fromkeys(column.values))[:MAX_VALUES]
        if not values:
            return ColumnScores(note="empty")
        alpha_heavy = sum(c.isalpha() for v in values for c in v) > 0.6 * sum(map(len, values))
        phone_region = region if alpha_heavy else best_phone_region(values, region=region)
        scores: dict[str, float] = {}
        for field_id, check in (
            {**checks, **cell_checks(phone_region)}.items() if phone_region != region else checks.items()
        ):
            if alpha_heavy and field_id in _NUMERIC_ONLY:
                continue
            # Most checks fail on most columns: stop after a probe with no hits.
            hits = sum(1 for v in values[:PROBE_VALUES] if check(v))
            if not hits:
                continue
            hits += sum(1 for v in values[PROBE_VALUES:] if check(v))
            if hits:
                scores[field_id] = hits / len(values) * _STRENGTH.get(field_id, 0.5)
        _adjust(scores, column=column, values=values)
        return ColumnScores(scores=scores, region=phone_region if scores.get("selector.phone") else None)


def _adjust(scores: dict[str, float], *, column: ColumnSample, values: list[str]) -> None:
    """Column-level evidence a per-cell check can't see."""
    distinct_ratio = len(set(column.values)) / max(len(column.values), 1)
    mean_length = sum(map(len, values)) / len(values)
    mean_tokens = sum(len(v.split()) for v in values) / len(values)

    single_names = [v for v in values if _is_name_like(v) and len(v.split()) == 1]
    if single_names:
        known = sum(map(_is_known_given, single_names)) / len(single_names)
        surnameish = sum(1 for v in single_names if _SURNAME.search(v)) / len(single_names)
        scores["person.given_name"] = scores.get("person.given_name", 0) * (0.6 + 1.2 * known)
        scores["person.surname"] = scores.get("person.surname", 0) * (0.6 + 1.2 * surnameish)
    if "person.full_name" in scores:
        known = sum(1 for v in values if any(_is_known_given(t) for t in v.split()[:3])) / len(values)
        scores["person.full_name"] *= 0.8 + 0.4 * known

    dates = [d for v in values if (d := parse_date(v)[0]) is not None]
    if len(dates) > 3 and "person.date_of_birth" in scores:
        years = [d.year for d in dates]
        spread = statistics.pstdev(years)
        median_age = datetime.now().year - statistics.median(years)
        plausible = spread >= 5 and 12 <= median_age <= 90
        scores["person.date_of_birth"] *= 1.4 if plausible else 0.3
        if plausible:
            scores["time.date"] = scores.get("time.date", 0) * 0.6

    if "key.row_id" in scores:
        head = [int(v) for v in column.values[:50] if _INT.match(v)]
        sequential = len(head) > 10 and all(b > a for a, b in zip(head, head[1:], strict=False))
        uuids = sum(1 for v in values if _UUID.match(v)) > 0.9 * len(values)
        scores["key.row_id"] *= 4.0 if distinct_ratio > 0.98 and (sequential or uuids) else 0.2
    if "key.reference" in scores and distinct_ratio < 0.9:
        scores["key.reference"] *= 0.3
    if "selector.bank_card" in scores and "selector.imei" in scores:
        fifteen = sum(1 for v in values if len(re.sub(r"\D", "", v)) == 15) / len(values)
        scores["selector.bank_card"] *= 1 - 0.6 * fifteen
    if "selector.phone" in scores and (
        scores.get("selector.imei", 0) >= 0.9 * scores["selector.phone"] or scores.get("time.epoch", 0) >= 0.5
    ):
        scores["selector.phone"] *= 0.5
    ints = [int(v) for v in values if _INT.match(v)]
    if "edge.amount" in scores and len(ints) > 0.9 * len(values):
        scores["edge.amount"] *= 0.4
    if "time.duration" in scores and ints and max(ints) <= 120:
        scores["time.duration"] *= 0.3
    if "person.age" in scores and ints and not (15 <= statistics.median(ints) <= 90):
        scores["person.age"] *= 0.3
    if mean_length > 40 and mean_tokens > 6:
        scores["other.free_text"] = 0.8
    elif distinct_ratio < 0.05 and len(set(values)) <= 30 and not any(v > 0.3 for v in scores.values()):
        scores["other.category"] = 0.35
    if mean_tokens > 6:
        for field_id in ("person.full_name", "organization.name", "location.city", "location.country"):
            scores.pop(field_id, None)
