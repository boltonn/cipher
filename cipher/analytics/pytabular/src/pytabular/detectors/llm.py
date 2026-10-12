"""LLM detector: the whole table preview to pyprompt's `columns` pack (field types, roles, row relationships)."""

import asyncio

from cipher.schemas.graph.ontology import RELATIONSHIPS, RelationshipType
from pytabular.detectors import ColumnScores, EdgeHint, TableContext
from pytabular.fields import field_types
from pytabular.profile import ColumnSample

PROPOSED_VERBS: dict[str, str] = {
    "interacted_with": "Any other interaction between the two parties on that row (not in the ontology yet).",
}
_ROW_VERBS = (
    RelationshipType.HAS_SELECTOR,
    RelationshipType.MEMBER_OF,
    RelationshipType.EMPLOYED_BY,
    RelationshipType.PART_OF,
    RelationshipType.LOCATED_IN,
    RelationshipType.EMAILED,
    RelationshipType.CALLED,
    RelationshipType.MESSAGED,
    RelationshipType.PAID,
    RelationshipType.FAMILY_OF,
    RelationshipType.OWNS,
)
LLM_SCORE = 0.9


def row_verbs() -> dict[str, str]:
    """Ontology verbs a table row can carry, plus the proposed interaction verbs."""
    return {**{v.value: RELATIONSHIPS[v].description for v in _ROW_VERBS}, **PROPOSED_VERBS}


def table_preview(columns: list[ColumnSample], context: TableContext, *, rows: int = 10, width: int = 60) -> str:
    """A pipe table: `#index header` per column, then the first sample rows."""
    header = " | ".join(f"#{c.index} {c.header if context.has_header else ''}".strip() for c in columns)
    body = [
        " | ".join(
            (row[c.index] if c.index < len(row) else "")[:width].replace("|", "/").replace("\n", " ") for c in columns
        )
        for row in context.preview_rows[:rows]
    ]
    return "\n".join([f"| {header} |", *[f"| {line} |" for line in body]])


def _default_runner():
    from pyprompt import PromptRunner, Settings

    return PromptRunner(Settings())


class LlmDetector:
    name = "llm"

    def __init__(self, runner=None, *, model: str | None = None):
        self._runner = runner
        self._model = model
        self._edges: list[EdgeHint] = []

    def score(self, columns: list[ColumnSample], *, context: TableContext) -> list[ColumnScores]:
        """One structured call per table; the chosen type scores `LLM_SCORE`, its role rides along."""
        descriptions = {f.id: f.description for f in field_types().values()}
        # A fresh runner per call: each `asyncio.run` is a new event loop, and an async client can't outlive its loop.
        owned = self._runner is None
        runner = self._runner or _default_runner()

        async def call():
            try:
                return await runner.type_table_columns(
                    table_preview(columns, context), field_types=descriptions, verbs=row_verbs(), model=self._model
                )
            finally:
                if owned:
                    await runner.aclose()

        output = asyncio.run(call())
        by_index = {c.index: c for c in output.columns}
        self._edges = [EdgeHint(src_role=r.from_role, dst_role=r.to_role, verb=r.verb) for r in output.relationships]
        return [
            ColumnScores(scores={hit.field_type: LLM_SCORE}, role=hit.role or None)
            if (hit := by_index.get(c.index))
            else ColumnScores()
            for c in columns
        ]

    def edge_hints(self) -> list[EdgeHint]:
        """Relationships the model read off the last table."""
        return self._edges
