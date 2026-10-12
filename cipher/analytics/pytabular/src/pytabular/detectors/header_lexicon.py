"""Header detector: match a column header against multilingual synonyms; leftover words name its role."""

from pytabular.detectors import ColumnScores, TableContext
from pytabular.fields import header_synonyms, is_spaceless, normalize_header, role_synonyms
from pytabular.profile import ColumnSample, is_number

_EXACT_ONLY_LENGTH = 2
_INFLECTING_ENDINGS = frozenset("ьйаяоеёиыуюaeiouy")


def _token_match(header_token: str, synonym_token: str) -> bool:
    """Equal, or an inflected form: `телефона` ~ `телефон`, `отправителя` ~ `отправитель` (last letter may change)."""
    if header_token == synonym_token:
        return True
    if len(synonym_token) < 4 or abs(len(header_token) - len(synonym_token)) > 3:
        return False
    # Only a final vowel / soft sign inflects away (`отправитель` -> `отправителя`); `caller` must not match `called`.
    stem = synonym_token[:-1] if len(synonym_token) >= 6 and synonym_token[-1] in _INFLECTING_ENDINGS else synonym_token
    return header_token.startswith(stem)


def _match(tokens: list[str], synonym: str) -> tuple[int, int] | None:
    """Token span of `synonym` inside the header tokens, if it occurs contiguously."""
    parts = synonym.split()
    for start in range(len(tokens) - len(parts) + 1):
        if all(_token_match(tokens[start + i], p) for i, p in enumerate(parts)):
            return start, start + len(parts)
    return None


def match_role(tokens: list[str], *, allow_short: bool = True) -> str | None:
    """The role named by leftover header words (`отправителя` -> `sender`).

    One- and two-letter roles (`a`/`b` party) only count beside a matched field (`A number`), never alone (`col_a`).
    """
    best: tuple[int, str] | None = None
    for role, synonyms in role_synonyms().items():
        for synonym in synonyms:
            short = len(synonym) <= _EXACT_ONLY_LENGTH and not is_spaceless(synonym)
            if short and (not allow_short or synonym not in tokens):
                continue
            found = synonym in "".join(tokens) if is_spaceless(synonym) else _match(tokens, synonym)
            if found and (best is None or len(synonym) > best[0]):
                best = (len(synonym), role)
    return best[1] if best else None


def score_header(header: str) -> ColumnScores:
    """Field scores for one header plus the role its leftover words name."""
    key = normalize_header(header)
    if not key:
        return ColumnScores()
    tokens = key.split()
    scores: dict[str, float] = {}
    spans: dict[str, tuple[int, int]] = {}
    spaceless = is_spaceless(key)
    for field_id, synonyms in header_synonyms().items():
        for synonym in synonyms:
            if synonym == key:
                score, span = 1.0, (0, len(tokens))
            elif spaceless and is_spaceless(synonym) and synonym in key:
                score, span = 0.7 + 0.25 * len(synonym) / len(key), (0, 0)
            elif len(synonym) <= _EXACT_ONLY_LENGTH:
                if synonym not in tokens:
                    continue
                score, span = 0.8, (tokens.index(synonym), tokens.index(synonym) + 1)
            elif (span := _match(tokens, synonym)) is not None:
                score = 0.7 + 0.25 * len(synonym) / len(key)
            else:
                continue
            # English compounds put the head noun last (`message_status` is a status).
            if span[1] == len(tokens) and len(tokens) > 1 and key.isascii():
                score += 0.1
            if score > scores.get(field_id, 0.0):
                scores[field_id], spans[field_id] = score, span
    if scores:
        best = max(scores.values())
        scores = {k: v if v >= best - 0.02 else v * 0.5 for k, v in scores.items()}
    role = None
    if scores:
        start, end = spans[max(scores, key=scores.__getitem__)]
        leftover = tokens[:start] + tokens[end:]
        role = match_role(leftover) if leftover else None
    else:
        role = match_role(tokens, allow_short=False)
    return ColumnScores(scores=scores, role=role)


_TEXTUAL_GROUPS = (
    "person.",
    "organization.name",
    "organization.industry",
    "location.city",
    "location.country",
    "location.admin_area",
    "location.street",
    "location.place_name",
)
_NUMERIC_EXCEPTIONS = {"person.age"}


def _mostly_numeric(column: ColumnSample) -> bool:
    values = column.values[:200]
    return bool(values) and sum(map(is_number, values)) >= 0.8 * len(values)


class HeaderLexiconDetector:
    name = "header"

    def score(self, columns: list[ColumnSample], *, context: TableContext) -> list[ColumnScores]:
        """Header synonyms; nothing for synthetic `column_N` names. Text fields over numeric cells are discounted."""
        if not context.has_header:
            return [ColumnScores() for _ in columns]
        out = []
        for column in columns:
            scores = score_header(column.header)
            if _mostly_numeric(column):
                scores.scores = {
                    k: v * 0.4 if k.startswith(_TEXTUAL_GROUPS) and k not in _NUMERIC_EXCEPTIONS else v
                    for k, v in scores.scores.items()
                }
            out.append(scores)
        return out
