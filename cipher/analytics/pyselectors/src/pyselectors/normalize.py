"""Stage 3 -- canonicalization of a raw selector substring.

Everything here is a pure function. ``fold_digits`` is length-preserving so
offsets computed on the folded text still index the original 1:1.
"""

import ipaddress
import re

import phonenumbers

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType

# Loose language -> default phone region. Only used when no explicit region is
# given and a number carries no country code of its own.
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


def fold_digits(text: str) -> str:
    """Map Arabic-Indic / Persian digits to ASCII, preserving length and every offset."""
    return text.translate(_DIGIT_FOLD)


def region_for(*, language: str | None, region: str | None) -> str | None:
    """Resolve the phone-parsing region from an explicit value or a language hint."""
    if region:
        return region.upper()
    if language:
        return _LANGUAGE_REGION.get(language.lower()[:2])
    return None


def normalize_phone(raw: str, *, region: str | None) -> str | None:
    """Return an E.164 string, or None if the number is not valid."""
    candidate = raw.strip()
    if candidate.startswith("00"):
        candidate = "+" + candidate[2:]
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


NORMALIZERS = {
    "phone": lambda raw, *, country=None, subtype=None: normalize_phone(raw, region=country),
    "email": lambda raw, *, country=None, subtype=None: normalize_email(raw),
    "iban": lambda raw, *, country=None, subtype=None: normalize_iban(raw),
    "imei": lambda raw, *, country=None, subtype=None: normalize_imei(raw),
    "imsi": lambda raw, *, country=None, subtype=None: normalize_digits_only(raw),
    "bank_card": lambda raw, *, country=None, subtype=None: normalize_digits_only(raw),
    "passport": lambda raw, *, country=None, subtype=None: normalize_passport_mrz(raw),
    "ip": lambda raw, *, country=None, subtype=None: normalize_ip(raw),
    "national_id": lambda raw, *, country=None, subtype=None: normalize_national_id(raw),
    "crypto_address": lambda raw, *, country=None, subtype=None: normalize_crypto_address(raw, subtype=subtype),
    "social_handle": lambda raw, *, country=None, subtype=None: normalize_social_handle(raw, subtype=subtype),
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
