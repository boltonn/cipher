"""Canonicalization of raw selector strings."""

import phonenumbers

# Loose language -> default phone region. Only used when no explicit region is
# given and a number has no country code of its own.
_LANGUAGE_REGION = {
    "en": "US",
    "ru": "RU",
    "uk": "UA",
    "zh": "CN",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
}


def region_for(*, language: str | None, region: str | None) -> str | None:
    """Resolve the phone-parsing region from an explicit value or a language hint."""
    if region:
        return region.upper()
    if language:
        return _LANGUAGE_REGION.get(language.lower()[:2])
    return None


def normalize_phone(raw: str, *, region: str | None) -> str | None:
    """Return an E.164 string, or None if the number is not valid."""
    try:
        parsed = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_email(raw: str) -> str:
    """Lowercase and trim an email address."""
    return raw.strip().strip("<>").lower()


def normalize_iban(raw: str) -> str | None:
    """Return a compact, validated IBAN, or None."""
    from stdnum import iban

    try:
        return iban.validate(raw)
    except Exception:
        return None


def normalize_imei(raw: str) -> str | None:
    """Return a compact, Luhn-valid IMEI (14-16 digits), or None."""
    from stdnum import imei

    try:
        return imei.validate(raw)
    except Exception:
        return None
