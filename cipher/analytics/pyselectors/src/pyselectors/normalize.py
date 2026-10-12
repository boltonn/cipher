"""Stage 3 -- canonicalization of a raw selector substring.

Everything here is a pure function. ``fold_digits`` is length-preserving so
offsets computed on the folded text still index the original 1:1.
"""

import ipaddress
import re

import phonenumbers

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType
from pyselectors.domains import registrable_domain

# Loose language -> region, for country pattern overlays and validators (national ids).
# Never a phone's country: a number without its own country code stays national.
_LANGUAGE_REGION = {
    "en": "US",
    "ru": "RU",
    "uk": "UA",
    "zh": "CN",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "fa": "IR",
    "ar": "SA",
}

# Non-ASCII decimal digits -> ASCII. Arabic-Indic and Persian/Extended Arabic-Indic.
_DIGIT_FOLD = {c: ord("0") + (c - 0x0660) for c in range(0x0660, 0x066A)}
_DIGIT_FOLD.update({c: ord("0") + (c - 0x06F0) for c in range(0x06F0, 0x06FA)})

_AT_RE = re.compile(r"\s*(?:\[at\]|\(at\)|\bat\b)\s*", re.IGNORECASE)
_DOT_RE = re.compile(r"\s*(?:\[dot\]|\(dot\)|\bdot\b)\s*", re.IGNORECASE)
_HANDLE_DOMAINS = (
    r"t\.me|telegram\.me|telegram\.dog|instagram\.com|facebook\.com|fb\.com|fb\.me|"
    r"twitter\.com|x\.com|tiktok\.com|vk\.com|ok\.ru|weibo\.(?:com|cn)|douyin\.com|"
    r"wa\.me|whatsapp\.com/send\?phone=|splus\.ir|sapp\.ir|ble\.ir|rubika\.ir|eitaa\.com"
)
_HANDLE_URL_RE = re.compile(
    rf"^(?:https?://)?(?:www\.|api\.|v\.)?(?:{_HANDLE_DOMAINS})/(?:s/|u/|user/|profile/|share/user/)?",
    re.IGNORECASE,
)
# Platforms whose usernames are case-sensitive; everything else is lowercased.
_CASE_SENSITIVE_HANDLES = frozenset()


_PHONE_LABEL_RE = re.compile(r"^[^\d+(]+")
# a trailing extension (`ext 8200`, `x12`, `доб. 3`) is not part of the number
_EXTENSION_RE = re.compile(r"\s*(?:ext\.?|extension|x|#|доб\.?|вн\.?)\s*\d{1,6}\s*$", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(?:\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2}[-./]\d{4})\b")


def is_national_phone(value: str) -> bool:
    """A normalized phone with no country of its own (`normalize_phone` kept its digits)."""
    return not value.startswith("+")


def fold_digits(text: str) -> str:
    """Map Arabic-Indic / Persian digits to ASCII, preserving length and every offset."""
    return text.translate(_DIGIT_FOLD)


def region_for(*, language: str | None, region: str | None) -> str | None:
    """Resolve the overlay region from an explicit value or a language hint (never used to parse a phone)."""
    if region:
        return region.upper()
    if language:
        return _LANGUAGE_REGION.get(language.lower()[:2])
    return None


def normalize_phone(raw: str, *, region: str | None) -> str | None:
    """E.164 when the number states its country or the caller verified `region`, else its digits as written.

    `+44 20 7946 0958` / `0044 …` -> `+442079460958`; `215.895.2372` with no region -> `2158952372`
    (national, country unknown -- never guessed). None for an invalid international number, a
    national one outside 7-15 digits, or a date.
    """
    # a leading label (`T`, `Tel:`, `Phone`) and `+ 1` spacing hide a stated country code
    candidate = _PHONE_LABEL_RE.sub("", raw.strip())
    candidate = re.sub(r"^\+\s+", "+", candidate)
    if candidate.startswith("00"):
        candidate = "+" + candidate[2:]
    if not candidate.startswith("+") and not region:
        digits = "".join(ch for ch in _EXTENSION_RE.sub("", candidate) if ch.isdigit())
        return digits if 7 <= len(digits) <= 15 and not _DATE_RE.search(candidate) else None
    try:
        parsed = phonenumbers.parse(candidate, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_email(raw: str) -> str:
    """Lowercase, trim, and un-defang an email address."""
    value = raw.strip().strip("<>").strip()
    if "@" not in value:
        value = _AT_RE.sub("@", value, count=1)
    if value.count(".") == 0 or " dot " in raw.lower() or "[dot]" in raw.lower() or "(dot)" in raw.lower():
        value = _DOT_RE.sub(".", value)
    return value.lower()


def normalize_iban(raw: str) -> str | None:
    """Return a compact, mod-97-valid IBAN, or None."""
    from stdnum import iban

    try:
        return iban.validate(raw)
    except Exception:
        return None


def normalize_imei(raw: str) -> str | None:
    """Return a compact, Luhn-valid 15-digit IMEI, or None."""
    from stdnum import imei

    digits = re.sub(r"\D", "", raw)
    if len(digits) != 15:
        return None
    try:
        return imei.validate(digits)
    except Exception:
        return None


def normalize_ip(raw: str) -> str | None:
    """Return the canonical (compressed, lowercased) IP, or None."""
    try:
        return ipaddress.ip_address(raw.strip()).compressed
    except ValueError:
        return None


def normalize_crypto_address(raw: str, *, subtype: SelectorSubtype | None = None) -> str | None:
    """Trim; lowercase a bech32 BTC address; keep EIP-55 casing for everything else."""
    value = raw.strip()
    if not value:
        return None
    if value.lower().startswith(("bc1", "tb1")):
        return value.lower()
    return value


def normalize_social_handle(raw: str, *, subtype: SelectorSubtype | None = None) -> str | None:
    """Strip a profile URL / leading @, return the bare username (lowercased unless case-sensitive)."""
    value = _HANDLE_URL_RE.sub("", raw.strip())
    value = value.split("?", 1)[0].split("/", 1)[0].lstrip("@").strip()
    if not value:
        return None
    if subtype == SelectorSubtype.WHATSAPP:
        digits = re.sub(r"\D", "", value)
        return f"+{digits}" if digits else None
    return value if subtype in _CASE_SENSITIVE_HANDLES else value.lower()


def normalize_digits_only(raw: str) -> str | None:
    """Strip everything but ASCII digits (IMSI, bank card)."""
    digits = re.sub(r"\D", "", raw)
    return digits or None


def normalize_national_id(raw: str) -> str | None:
    """Strip separators, uppercase (keeps a CN trailing check ``X``)."""
    value = re.sub(r"[\s.\-/]", "", raw).upper()
    return value or None


def normalize_passport_mrz(raw: str) -> str | None:
    """Re-lay a matched MRZ block into fixed-width lines joined by newlines."""
    compact = re.sub(r"[^A-Z0-9<]", "", raw.upper())
    for width in (44, 36, 30):
        if len(compact) % width == 0 and len(compact) // width in (2, 3):
            n = len(compact) // width
            return "\n".join(compact[i * width : (i + 1) * width] for i in range(n))
    return None


def normalize_passport(raw: str) -> str | None:
    """An MRZ block re-laid into fixed-width lines, or a passport number compacted (`45 06 123456` -> `4506123456`)."""
    if "<" in raw:
        return normalize_passport_mrz(raw)
    value = re.sub(r"[\s.\-№#]", "", raw).upper()
    return value if 6 <= len(value) <= 10 and value.isalnum() and any(c.isdigit() for c in value) else None


_PLATE_LOOKALIKES = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")


def normalize_license_plate(raw: str) -> str | None:
    """Uppercase, separators dropped, Cyrillic letters that plates share with Latin mapped to Latin (`А123ВС 77` -> `A123BC77`)."""
    value = re.sub(r"[\s\-·.|]", "", raw).upper().translate(_PLATE_LOOKALIKES)
    return value if 4 <= len(value) <= 10 else None


def normalize_mac_address(raw: str) -> str | None:
    """Any of `AA-BB-CC-DD-EE-FF`, `aabb.ccdd.eeff`, `aa:bb:...` -> `aa:bb:cc:dd:ee:ff`."""
    digits = re.sub(r"[^0-9A-Fa-f]", "", raw).lower()
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2)) if len(digits) == 12 else None


NORMALIZERS = {
    "phone": lambda raw, *, country=None, subtype=None: normalize_phone(raw, region=country),
    "email": lambda raw, *, country=None, subtype=None: normalize_email(raw),
    "iban": lambda raw, *, country=None, subtype=None: normalize_iban(raw),
    "imei": lambda raw, *, country=None, subtype=None: normalize_imei(raw),
    "imsi": lambda raw, *, country=None, subtype=None: normalize_digits_only(raw),
    "bank_card": lambda raw, *, country=None, subtype=None: normalize_digits_only(raw),
    "passport": lambda raw, *, country=None, subtype=None: normalize_passport(raw),
    "license_plate": lambda raw, *, country=None, subtype=None: normalize_license_plate(raw),
    "mac_address": lambda raw, *, country=None, subtype=None: normalize_mac_address(raw),
    "ip": lambda raw, *, country=None, subtype=None: normalize_ip(raw),
    "national_id": lambda raw, *, country=None, subtype=None: normalize_national_id(raw),
    "crypto_address": lambda raw, *, country=None, subtype=None: normalize_crypto_address(raw, subtype=subtype),
    "social_handle": lambda raw, *, country=None, subtype=None: normalize_social_handle(raw, subtype=subtype),
    "domain": lambda raw, *, country=None, subtype=None: registrable_domain(raw),
}


def canonicalize(
    normalizer: str, raw: str, *, country: str | None = None, subtype: SelectorSubtype | None = None
) -> str | None:
    """Run the named normalizer over ``raw``; return the canonical value or None to drop."""
    fn = NORMALIZERS.get(normalizer)
    if fn is None:
        return raw.strip() or None
    return fn(raw, country=country, subtype=subtype)


def normalize_selector(
    selector_type: SelectorType, raw: str, region: str | None = None
) -> tuple[str | None, dict[str, str]]:
    """Canonicalize + validate a single analyst-entered value (used by the backend).

    Returns ``(normalized_value | None, attributes)``. A None value means the
    input failed validation for its type.
    """
    from pyselectors.packs.loader import load_pack
    from pyselectors.validate import SelectorRejected, run as run_validator

    country = region.upper() if region else None
    try:
        pack = load_pack(selector_type.value, country)
        normalizer, validator = pack.normalizer, pack.validator
    except FileNotFoundError:
        normalizer, validator = selector_type.value, selector_type.value

    value = canonicalize(normalizer, fold_digits(raw), country=country)
    if value is None:
        return None, {}
    if validator is None:
        return value, {}
    try:
        attrs = run_validator(selector_type, value, country=country)
    except SelectorRejected:
        return None, {}
    return value, attrs
