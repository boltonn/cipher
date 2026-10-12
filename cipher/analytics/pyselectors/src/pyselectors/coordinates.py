"""Find geographic coordinates in text and normalize them to decimal degrees.

Not part of the selector pipeline -- coordinates become ``location`` rows /
``LOCATION`` mentions, not selectors. Handles the formats seen across the
supported languages: decimal degrees, degrees-minutes-seconds, Russian
``с.ш./в.д.`` and Chinese ``北纬/东经`` hemisphere markers, comma decimals, and
``lat=/lon=`` style labels. To keep false positives down a bare ``12.3, 45.6``
pair is ignored -- a match needs a degree sign, a hemisphere marker, or a
lat/lon label.
"""

import regex

from cipher.schemas.graph.spans import CoordinateSpan
from pyselectors.normalize import fold_digits

_NUM = r"\d{1,3}(?:[.,]\d+)?"
_DEG = r"[°º˚]"
_MIN = r"['′’ʹ]"
_SEC = r'["″”ʺ]'
_SIGN = r"[-+]?"

_HEMI_N = r"N|С\.?\s?Ш\.?|СЕВ"
_HEMI_S = r"S|Ю\.?\s?Ш\.?|ЮЖ"
_HEMI_E = r"E|В\.?\s?Д\.?|ВОСТ"
_HEMI_W = r"W|З\.?\s?Д\.?|ЗАП"


def _dms(n: int) -> str:
    return (
        rf"(?P<d{n}>\d{{1,3}})\s*{_DEG}\s*"
        rf"(?:(?P<m{n}>{_NUM})\s*{_MIN}\s*)?(?:(?P<s{n}>{_NUM})\s*{_SEC}\s*)?"
    )


_DMS_PAIR = regex.compile(
    rf"(?<![\w.]){_dms(1)}(?P<h1>{_HEMI_N}|{_HEMI_S})\s*[,;\s]\s*"
    rf"{_dms(2)}(?P<h2>{_HEMI_E}|{_HEMI_W})",
    regex.VERSION1 | regex.IGNORECASE,
)

_DECIMAL_HEMI_PAIR = regex.compile(
    rf"(?<![\w.])(?P<lat>{_SIGN}{_NUM})[ \t]*{_DEG}?[ \t]*(?P<h1>{_HEMI_N}|{_HEMI_S})?[ \t]*[,;][ \t]*"
    rf"(?P<lon>{_SIGN}{_NUM})[ \t]*{_DEG}?[ \t]*(?P<h2>{_HEMI_E}|{_HEMI_W})?(?![\w.])",
    regex.VERSION1 | regex.IGNORECASE,
)

_CJK_PAIR = regex.compile(
    rf"(?P<h1>北纬|南纬)\s*(?P<lat>{_NUM})\s*{_DEG}?(?:\s*(?P<m1>{_NUM})\s*{_MIN})?\s*[,;\s]*"
    rf"(?P<h2>东经|西经)\s*(?P<lon>{_NUM})\s*{_DEG}?(?:\s*(?P<m2>{_NUM})\s*{_MIN})?",
    regex.VERSION1,
)

_LABELED = regex.compile(
    r"(?:lat(?:itude)?|широта|纬度)[\s:=]{0,4}(?P<lat>[-+]?\d{1,3}(?:[.,]\d+)?)"
    r"[^-+\d]{0,25}?(?:lon(?:g(?:itude)?)?|долгота|经度)[\s:=]{0,4}(?P<lon>[-+]?\d{1,3}(?:[.,]\d+)?)",
    regex.VERSION1 | regex.IGNORECASE,
)


def _f(value: str | None) -> float:
    return float(value.replace(",", ".")) if value else 0.0


def _dms_to_deg(d: str, m: str | None, s: str | None, hemi: str) -> float:
    deg = _f(d) + _f(m) / 60 + _f(s) / 3600
    if regex.match(rf"(?i)^(?:{_HEMI_S}|{_HEMI_W})", hemi.strip()):
        deg = -deg
    return deg


def _decimal_sign(value: str, hemi: str | None, negative: str) -> float:
    deg = _f(value)
    if hemi and regex.match(rf"(?i)^(?:{negative})", hemi.strip()):
        deg = -abs(deg)
    return deg


def extract_coordinates(text: str, *, language: str | None = None) -> list[CoordinateSpan]:
    """Every coordinate in ``text``, normalized to decimal degrees, sorted by offset."""
    if not text:
        return []
    folded = fold_digits(text)
    out: list[CoordinateSpan] = []

    for m in _DMS_PAIR.finditer(folded):
        lat = _dms_to_deg(m["d1"], m["m1"], m["s1"], m["h1"])
        lon = _dms_to_deg(m["d2"], m["m2"], m["s2"], m["h2"])
        _add(out, lat, lon, m, "dms" if not _is_cyrillic(m["h1"]) else "cyrillic", folded)

    for m in _DECIMAL_HEMI_PAIR.finditer(folded):
        has_decimal = "." in m["lat"] or "," in m["lat"] or "." in m["lon"] or "," in m["lon"]
        # a hemisphere letter alone on integer coords is too weak (tables, lists);
        # need a degree sign, or a decimal point plus a hemisphere/degree cue.
        if not (_DEG_IN(m.group(0)) or (has_decimal and (m["h1"] or m["h2"]))):
            continue
        lat = _decimal_sign(m["lat"], m["h1"], _HEMI_S)
        lon = _decimal_sign(m["lon"], m["h2"], _HEMI_W)
        _add(out, lat, lon, m, "cyrillic" if _is_cyrillic(m["h1"] or m["h2"] or "") else "decimal", folded)

    for m in _CJK_PAIR.finditer(folded):
        lat = _f(m["lat"]) + _f(m["m1"]) / 60
        lon = _f(m["lon"]) + _f(m["m2"]) / 60
        if m["h1"] == "南纬":
            lat = -lat
        if m["h2"] == "西经":
            lon = -lon
        _add(out, lat, lon, m, "cjk", folded)

    for m in _LABELED.finditer(folded):
        _add(out, _f(m["lat"]), _f(m["lon"]), m, "labeled", folded)

    out.sort(key=lambda c: (c.start_offset, c.end_offset))
    return _dedupe(out)


_AXIS = regex.compile(
    rf"^(?P<sign>[-+])?\s*(?P<d>\d{{1,3}}(?:[.,]\d+)?)\s*{_DEG}?\s*(?:(?P<m>{_NUM})\s*{_MIN}\s*)?"
    rf"(?:(?P<s>{_NUM})\s*{_SEC}\s*)?(?P<h>{_HEMI_N}|{_HEMI_S}|{_HEMI_E}|{_HEMI_W})?$",
    regex.VERSION1 | regex.IGNORECASE,
)
_BARE_PAIR = regex.compile(rf"^\(?\s*(?P<lat>{_SIGN}{_NUM})\s*[,;\s]\s*(?P<lon>{_SIGN}{_NUM})\s*\)?$")


def parse_degrees(value: str) -> tuple[float, str | None] | None:
    """One axis in one cell -- `55.7558`, `-37,6`, `55°45′N`, `37°37'E`, `55,75 с.ш.` -- to decimal degrees.

    Also returns the axis the hemisphere names (`lat` / `lon`), or None when the value doesn't say.
    """
    match = _AXIS.match(fold_digits(value.strip()))
    if match is None:
        return None
    degrees = _f(match["d"]) + _f(match["m"]) / 60 + _f(match["s"]) / 3600
    hemisphere = (match["h"] or "").strip()
    axis = None
    if hemisphere:
        axis = "lat" if regex.match(rf"(?i)^(?:{_HEMI_N}|{_HEMI_S})$", hemisphere) else "lon"
        if regex.match(rf"(?i)^(?:{_HEMI_S}|{_HEMI_W})$", hemisphere):
            degrees = -degrees
    if match["sign"] == "-":
        degrees = -degrees
    return degrees, axis


def parse_coordinate_cell(value: str) -> CoordinateSpan | None:
    """A latitude/longitude pair filling one table cell.

    Unlike `extract_coordinates`, a bare `55.7558, 37.6173` counts: in free text a
    number pair is too ambiguous, but a cell the column says is a coordinate isn't.
    """
    text = value.strip()
    spans = extract_coordinates(text)
    if spans and spans[0].end_offset - spans[0].start_offset >= 0.8 * len(text):
        return spans[0]
    match = _BARE_PAIR.match(fold_digits(text))
    if match is None or not ("." in match["lat"] + match["lon"] or "," in match["lat"] + match["lon"]):
        return None
    out: list[CoordinateSpan] = []
    _add(out, _f(match["lat"]), _f(match["lon"]), match, "decimal", text)
    return out[0] if out else None


def _add(out, lat, lon, m, fmt, text):  # noqa: ANN001, ANN202
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return
    if lat == 0 and lon == 0:
        return
    out.append(
        CoordinateSpan(
            latitude=round(lat, 6),
            longitude=round(lon, 6),
            raw_value=text[m.start() : m.end()],
            coordinate_format=fmt,
            start_offset=m.start(),
            end_offset=m.end(),
            confidence=0.85 if fmt in ("dms", "cyrillic", "cjk") else 0.7,
        )
    )


def _dedupe(spans: list[CoordinateSpan]) -> list[CoordinateSpan]:
    kept: list[CoordinateSpan] = []
    for span in spans:
        if any(k.start_offset < span.end_offset and span.start_offset < k.end_offset for k in kept):
            continue
        kept.append(span)
    return kept


def _is_cyrillic(marker: str | None) -> bool:
    return bool(marker) and any("Ѐ" <= ch <= "ӿ" for ch in marker)


def _DEG_IN(fragment: str) -> bool:  # noqa: N802
    return bool(regex.search(_DEG, fragment))
