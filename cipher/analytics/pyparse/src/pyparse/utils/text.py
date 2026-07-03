import re
from typing import Final
from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse

UNICODE_BULLETS: Final[list[str]] = [
    "\u0095",
    "\u2022",
    "\u2023",
    "\u2043",
    "\u3164",
    "\u204c",
    "\u204d",
    "\u2219",
    "\u25cb",
    "\u25cf",
    "\u25d8",
    "\u25e6",
    "\u2619",
    "\u2765",
    "\u2767",
    "\u29be",
    "\u29bf",
    "\u002d",
    "",
    r"\*",
    "\x95",
    "·",
]
BULLETS_PATTERN: Final[str] = "|".join(UNICODE_BULLETS)
UNICODE_BULLETS_RE: Final[re.Pattern] = re.compile(
    f"(?:{BULLETS_PATTERN})(?!{BULLETS_PATTERN})"
)

URL_RE: Final[re.Pattern] = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')


def clean_url_entropy(text: str, max_param_len: int = 32) -> str:
    """Finds URLs and truncates query parameter values that exceed a length threshold.

    This prevents high-entropy IDs/tokens from diluting embedding vectors.
    """

    def shrink_params(match: re.Match) -> str:
        url = match.group(0)
        try:
            parsed: ParseResult = urlparse(url)
            if not parsed.query:
                return url

            params = parse_qsl(parsed.query)
            new_params = []
            for k, v in params:
                # If a parameter value is longer than threshold, it's likely an ID/Token
                if len(v) > max_param_len:
                    # Keep the first 8 chars for some context, then truncate
                    new_params.append((k, f"{v[:8]}..."))
                else:
                    new_params.append((k, v))

            return urlunparse(parsed._replace(query=urlencode(new_params)))
        except Exception:
            return url

    return URL_RE.sub(shrink_params, text)


def clean_non_ascii_chars(text: str) -> str:
    """Cleans non-ascii characters from unicode string."""
    return text.encode("ascii", "ignore").decode()


def clean_bullets(text: str, replace: str = "*") -> str:
    """Cleans unicode bullets from the start of a section of text."""
    search = UNICODE_BULLETS_RE.match(text)
    if search is None:
        return text
    return UNICODE_BULLETS_RE.sub(replace, text, 1).strip()


def clean_ordered_bullets(text: str) -> str:
    """Cleans numeric/alphanumeric bulleted text sections (e.g., '1.1', 'a.b')."""
    text_sp = text.split()
    if not text_sp:
        return text

    if any(["." not in text_sp[0], ".." in text_sp[0]]):
        return text

    bullet = re.split(pattern=r"[\.]", string=text_sp[0])
    if not bullet[-1]:
        del bullet[-1]

    if len(bullet[0]) > 2:
        return text

    return " ".join(text_sp[1:])


def clean_ligatures(text: str) -> str:
    """Replaces ligatures with their most likely equivalent characters."""
    ligatures_map = {
        "æ": "ae",
        "Æ": "AE",
        "ﬀ": "ff",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "ﬅ": "ft",
        "ʪ": "ls",
        "œ": "oe",
        "Œ": "OE",
        "ȹ": "qp",
        "ﬆ": "st",
        "ʦ": "ts",
    }
    for k, v in ligatures_map.items():
        text = text.replace(k, v)
    return text


def replace_unicode_quotes(text: str) -> str:
    """Replaces common mojibake and unicode characters with standard equivalents."""
    replacements = {
        "\x91": "‘",
        "\x92": "’",
        "\x93": "“",
        "\x94": "”",
        "&apos;": "'",
        "â\x80\x99": "'",
        "â\x80“": "—",
        "â\x80”": "–",
        "â\x80˜": "‘",
        "â\x80¦": "…",
        "â\x80™": "’",
        "â\x80œ": "“",
        "â\x80?": "”",
        "â\x80ť": "”",
        "â\x80ś": "“",
        "â\x80¨": "—",
        "â\x80ł": "″",
        "â\x80Ž": "",
        "â\x80‚": "",
        "â\x80‰": "",
        "â\x80‹": "",
        "â\x80": "",
        "â\x80s'": "",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def clean_extra_whitespace(text: str) -> str:
    """Normalizes line breaks and collapses multiple spaces/tabs."""
    # Handle line breaks first
    text = re.sub(r"\r\n", "\n", text)
    # Collapse multiple newlines into single newlines
    text = re.sub(r"\n{2,}", "\n", text)
    # Replace non-breaking spaces and single newlines with space for sentence flow
    text = re.sub(r"[\xa0\n\t]", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"([ ]{2,})", " ", text)
    return text.strip()


def clean_trailing_punctuation(text: str) -> str:
    """Strips trailing punctuation commonly found in headings or lists."""
    return text.strip().rstrip(".,:;")


def clean_text(
    text: str | None,
    *,
    extra_whitespace: bool = False,
    trailing_punctuation: bool = True,
    lowercase: bool = False,
    ensure_ascii: bool = True,
    normalize_urls: bool = True,
    max_url_param_len: int = 32,
) -> str:
    """Unified cleaning entry point for text processing."""
    if text is None:
        return ""

    cleaned_text = text.lower() if lowercase else text

    # 1. Structural URL cleaning (Entropy reduction)
    if normalize_urls:
        cleaned_text = clean_url_entropy(cleaned_text, max_param_len=max_url_param_len)

    # 2. Encoding / Mojibake fixes
    cleaned_text = replace_unicode_quotes(cleaned_text)
    cleaned_text = clean_ligatures(cleaned_text)

    # 3. Structural cleaning
    if trailing_punctuation:
        cleaned_text = clean_trailing_punctuation(cleaned_text)

    if extra_whitespace:
        cleaned_text = clean_extra_whitespace(cleaned_text)

    # 4. Final filter
    if ensure_ascii:
        cleaned_text = clean_non_ascii_chars(cleaned_text)

    return cleaned_text.strip()
