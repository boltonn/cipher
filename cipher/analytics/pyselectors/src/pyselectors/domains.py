"""Web domains: recognise a URL / bare domain and reduce it to its registrable domain.

`https://click.e.target.com/terms?x=1` and `Target.com` both reduce to `target.com`,
the site an organization owns. Shared by the `domain` selector pack and by NER,
which drops name spans that are really (part of) a web address.
"""

import re

# Deliberately curated rather than the full public-suffix list: a bare word like
# `report.pdf` or `main.py` must not read as a domain.
_TLD_WORDS = (
    "com org net edu gov mil int io co ai app dev info biz me tv ly us uk ca au de fr es it nl se no dk fi ch at be "
    "ie pl ru ua cn jp kr in br mx nz za eu xyz tech online site store shop news blog cloud ir il tr sg hk tw"
)
TLDS = frozenset(_TLD_WORDS.split())
# Second-level public suffixes: `bbc.co.uk` is registrable, `co.uk` is not.
_SECOND_LEVEL_WORDS = (
    "co.uk org.uk ac.uk gov.uk com.au net.au org.au co.nz co.jp co.in co.za co.il co.kr "
    "com.br com.cn com.mx com.sg com.hk com.tr com.tw"
)
_SECOND_LEVEL = frozenset(_SECOND_LEVEL_WORDS.split())
_HOST_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
_URL_PREFIX_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:www\d?\.)?", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)]}>\"'"
_LEADING_PUNCT = "([{<\"'"


def registrable_domain(raw: str) -> str | None:
    """`Target.com/terms` -> `target.com`; None when ``raw`` isn't a web address on a known TLD."""
    value = _URL_PREFIX_RE.sub("", raw.strip().rstrip(_TRAILING_PUNCT))
    host = re.split(r"[/?#:]", value, maxsplit=1)[0].lower().rstrip(".")
    if "@" in host or not _HOST_RE.match(host):
        return None
    labels = host.split(".")
    if labels[-1] not in TLDS:
        return None
    keep = 3 if len(labels) >= 3 and ".".join(labels[-2:]) in _SECOND_LEVEL else 2
    if len(labels) < keep:
        return None
    return ".".join(labels[-keep:])


def site_name(domain: str) -> str:
    """The name part of a registrable domain: `bestbuy.com` -> `bestbuy`, `bbc.co.uk` -> `bbc`."""
    return domain.split(".", 1)[0]


def is_web_address(text: str) -> bool:
    """Whether the whole of ``text`` is one URL / domain (`Udemy.com`, `www.x.org/a`), not prose containing one."""
    token = text.strip().rstrip(_TRAILING_PUNCT)
    return bool(token) and not any(c.isspace() for c in token) and registrable_domain(token) is not None


def web_host_containing(content: str, start: int, end: int) -> str | None:
    """The registrable domain whose host ``content[start:end]`` sits in, else None.

    `Towards` at its offsets in `read towardsdatascience.com today` -> `towardsdatascience.com`;
    a word in the path (`upenn.edu/usa`) or a standalone `Dell` -> None.
    """
    lo, hi = start, end
    while lo > 0 and not content[lo - 1].isspace():
        lo -= 1
    while hi < len(content) and not content[hi].isspace():
        hi += 1
    while lo < start and content[lo] in _LEADING_PUNCT:
        lo += 1
    token = content[lo:hi]
    if not is_web_address(token):
        return None
    scheme = token.find("://")
    host_from = scheme + 3 if scheme >= 0 else 0
    host_end = next((i for i in range(host_from, len(token)) if token[i] in "/?#:"), len(token))
    return registrable_domain(token) if end <= lo + host_end else None
