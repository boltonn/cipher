"""Column-typing detectors. Each scores every column against the field vocabulary, so any mix can be compared."""

from dataclasses import dataclass, field
from typing import Protocol

from pytabular.profile import ColumnSample


@dataclass(slots=True)
class TableContext:
    """Table-level facts a detector may use besides the column itself."""

    headers: list[str]
    has_header: bool
    preview_rows: list[list[str]] = field(default_factory=list)
    region: str | None = None
    """ISO-3166 alpha-2 default region for phone validation (from the user, or the table's script)."""


@dataclass(slots=True)
class ColumnScores:
    """One detector's verdict on one column."""

    scores: dict[str, float] = field(default_factory=dict)
    role: str | None = None
    note: str | None = None
    region: str | None = None
    """Phone region under which the column validates (validators only)."""

    def top(self, n: int = 5) -> dict[str, float]:
        """The `n` best non-zero scores, rounded."""
        best = sorted(((k, v) for k, v in self.scores.items() if v > 0), key=lambda kv: -kv[1])[:n]
        return {k: round(v, 3) for k, v in best}


@dataclass(frozen=True, slots=True)
class EdgeHint:
    """A relationship a detector read off the table (only the LLM proposes these)."""

    src_role: str
    dst_role: str
    verb: str


class Detector(Protocol):
    name: str

    def score(self, columns: list[ColumnSample], *, context: TableContext) -> list[ColumnScores]:
        """One `ColumnScores` per column, in order."""
        ...


class ProposesEdges(Protocol):
    def edge_hints(self) -> list[EdgeHint]:
        """Edges proposed during the last `score` call."""
        ...
