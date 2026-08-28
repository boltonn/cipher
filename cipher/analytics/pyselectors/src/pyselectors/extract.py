"""Find and normalize selectors in a block of text.

All matchers report character offsets into the exact input string, so a caller
can store them directly as `mention.start_offset` / `end_offset` against
`ExtractedText.content`.
"""

import re

import phonenumbers
from phonenumbers import Leniency, PhoneNumberMatcher

from pyselectors.normalize import (
    normalize_email,
    normalize_iban,
    normalize_imei,
    region_for,
)
from pyselectors.schemas import SelectorKind, SelectorSpan

_EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?![\w-])")
# IBAN, tolerating the spaced 4-char grouping it is usually written in. Groups
# are pinned to 4 chars (last group 1-4) so it can't run on into following words.
_IBAN_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?:[ ]?[A-Za-z0-9]{4}){2,7}(?:[ ]?[A-Za-z0-9]{1,4})?(?![A-Za-z0-9])"
)
# Exactly 15 digits (the IMEI length), optionally separated, not inside a longer token.
_IMEI_RE = re.compile(r"(?<![\w.])(?:\d[ \-]?){14}\d(?![\w.])")
# Passport machine-readable zone header: "P<" + 3-letter issuing country.
_MRZ_RE = re.compile(r"P<[A-Z<]{3}[A-Z0-9<]{5,}")


def extract_selectors(
    text: str, *, language: str | None = None, region: str | None = None
) -> list[SelectorSpan]:
    """Extract phone, email, IBAN, IMEI, and MRZ-passport selectors from `text`."""
    if not text:
        return []

    resolved_region = region_for(language=language, region=region)
    spans: list[SelectorSpan] = []
    spans.extend(_phones(text, resolved_region))
    spans.extend(_emails(text))
    spans.extend(_ibans(text))
    spans.extend(_imeis(text))
    spans.extend(_passports(text))
    spans.sort(key=lambda s: (s.start_offset, s.end_offset))
    return spans


def _phones(text: str, region: str | None) -> list[SelectorSpan]:
    out: list[SelectorSpan] = []
    for match in PhoneNumberMatcher(text, region or "ZZ", leniency=Leniency.VALID):
        e164 = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
        out.append(
            SelectorSpan(
                selector_kind=SelectorKind.PHONE,
                raw_value=match.raw_string,
                normalized_value=e164,
                start_offset=match.start,
                end_offset=match.end,
                confidence=0.9,
                region_hint=region,
            )
        )
    return out


def _emails(text: str) -> list[SelectorSpan]:
    return [
        SelectorSpan(
            selector_kind=SelectorKind.EMAIL,
            raw_value=m.group(0),
            normalized_value=normalize_email(m.group(0)),
            start_offset=m.start(),
            end_offset=m.end(),
            confidence=0.98,
        )
        for m in _EMAIL_RE.finditer(text)
    ]


def _ibans(text: str) -> list[SelectorSpan]:
    out: list[SelectorSpan] = []
    for m in _IBAN_RE.finditer(text):
        normalized = normalize_iban(m.group(0))
        if normalized:
            out.append(
                SelectorSpan(
                    selector_kind=SelectorKind.IBAN,
                    raw_value=m.group(0),
                    normalized_value=normalized,
                    start_offset=m.start(),
                    end_offset=m.end(),
                    confidence=0.97,
                )
            )
    return out


def _imeis(text: str) -> list[SelectorSpan]:
    out: list[SelectorSpan] = []
    for m in _IMEI_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) != 15:
            continue
        normalized = normalize_imei(digits)
        if normalized:
            out.append(
                SelectorSpan(
                    selector_kind=SelectorKind.IMEI,
                    raw_value=m.group(0),
                    normalized_value=normalized,
                    start_offset=m.start(),
                    end_offset=m.end(),
                    confidence=0.75,
                )
            )
    return out


def _passports(text: str) -> list[SelectorSpan]:
    return [
        SelectorSpan(
            selector_kind=SelectorKind.PASSPORT,
            raw_value=m.group(0),
            normalized_value=m.group(0).replace("<", "").upper(),
            start_offset=m.start(),
            end_offset=m.end(),
            confidence=0.6,
        )
        for m in _MRZ_RE.finditer(text)
    ]
