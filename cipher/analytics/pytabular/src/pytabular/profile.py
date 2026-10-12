"""Sampled columns and their cheap statistics (null rate, distinctness, script, character shapes)."""

import re
from collections import Counter
from dataclasses import dataclass, field

from cipher.names import dominant_script
from cipher.schemas.ingestion.table_mapping import ColumnProfile

NULL_TOKENS = frozenset(
    {"", "null", "none", "nan", "n/a", "na", "-", "--", "—", "nil", "undefined", "#n/a", "нет данных"}
)
_NUMBER = re.compile(r"^[-+]?(\d{1,3}([ ,. ']\d{3})+|\d+)([.,]\d+)?$")
_MULTI_DELIMITERS = (";", "|", ",", "\n")


def is_null(value: str) -> bool:
    """Empty or a null placeholder."""
    return value.strip().lower() in NULL_TOKENS


def is_number(value: str) -> bool:
    """Plain or thousands-grouped number, `.` or `,` decimals."""
    return bool(_NUMBER.match(value.strip()))


def shape(value: str, *, limit: int = 24) -> str:
    """Character-class shape with runs collapsed: `+7 916 123` -> `+d d d`, `Ivan Petrov` -> `Aa Aa`."""
    out: list[str] = []
    for ch in value[:limit]:
        if ch.isdigit():
            token = "d"
        elif ch.isalpha():
            token = "A" if ch.isupper() else "a"
        elif ch.isspace():
            token = " "
        else:
            token = ch
        if not out or out[-1] != token:
            out.append(token)
    return "".join(out)


@dataclass(slots=True)
class ColumnSample:
    """One column's sampled cells (head + spread), with the empties and placeholders dropped."""

    index: int
    header: str
    values: list[str] = field(default_factory=list)
    sampled: int = 0

    @property
    def distinct(self) -> list[str]:
        """Distinct values, first-seen order."""
        return list(dict.fromkeys(self.values))

    def preview(self, n: int = 8) -> list[str]:
        """Up to `n` distinct, mid-length example values (avoids a run of one repeated value)."""
        return [v[:80] for v in self.distinct[:n]]


def build_columns(headers: list[str], rows: list[list[str]]) -> list[ColumnSample]:
    """Transpose sampled rows into `ColumnSample`s (ragged rows padded)."""
    columns = [ColumnSample(index=i, header=h) for i, h in enumerate(headers)]
    for row in rows:
        for column in columns:
            column.sampled += 1
            value = row[column.index].strip() if column.index < len(row) else ""
            if not is_null(value):
                column.values.append(value)
    return columns


def profile_column(column: ColumnSample) -> ColumnProfile:
    """Statistics the detectors and the UI share."""
    values = column.values
    if not values:
        return ColumnProfile(sampled=column.sampled, null_rate=1.0)
    joined = "".join(values)
    chars = max(len(joined), 1)
    shapes = Counter(shape(v) for v in values)
    return ColumnProfile(
        sampled=column.sampled,
        null_rate=1 - len(values) / max(column.sampled, 1),
        distinct_ratio=len(set(values)) / len(values),
        mean_length=sum(map(len, values)) / len(values),
        max_length=max(map(len, values)),
        digit_ratio=sum(c.isdigit() for c in joined) / chars,
        alpha_ratio=sum(c.isalpha() for c in joined) / chars,
        script=dominant_script(joined[:5000]).value,
        shapes=[s for s, _ in shapes.most_common(3)],
        multi_value_delimiter=_multi_value_delimiter(values),
    )


def _multi_value_delimiter(values: list[str]) -> str | None:
    """A delimiter present in most cells, splitting them into similar-looking parts (`a@x.com; b@y.com`)."""
    for delimiter in _MULTI_DELIMITERS:
        split = [v.split(delimiter) for v in values[:200] if delimiter in v]
        if len(split) < 0.3 * min(len(values), 200):
            continue
        parts = [p.strip() for row in split for p in row if p.strip()]
        if parts and len(Counter(shape(p) for p in parts).most_common(1)[0][0]) > 1 and all(len(p) < 60 for p in parts):
            first = Counter(shape(p) for p in parts).most_common(1)[0][1]
            if first / len(parts) > 0.6:
                return delimiter
    return None
