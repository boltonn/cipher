"""Turn detector scores into column decisions, slots and edges -- the `TableMapping` for one sheet.

Cascade: the cheap detectors (`header`, `validators`) score every column. Model
detectors run afterwards, in the order given, and only while some column is still
below `accept_threshold`. Scores are a weighted average over the detectors that
had an opinion, plus a bonus when detectors agree. Columns, slots and edges a user
set in `locked` are kept and everything else is re-evaluated around them.
"""

import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from cipher.schemas.graph.ontology import SelectorSubtype
from cipher.schemas.ingestion.table_mapping import (
    OTHER_FIELD,
    ColumnDecision,
    ColumnTransform,
    DetectorEvidence,
    MappingDecisionSource,
    TableFormat,
    TableMapping,
    TableSample,
    TableSheetLayout,
)
from pytabular.detectors import ColumnScores, Detector, EdgeHint, TableContext
from pytabular.detectors.validators import DISPROVABLE, hit_rate, parse_float, region_hint
from pytabular.fields import field_type, normalize_header
from pytabular.header import HeaderGuess, data_rows, detect_header
from pytabular.profile import ColumnSample, build_columns, profile_column
from pytabular.reader import TableSource
from pytabular.slots import build_slots

CHEAP_DETECTORS = frozenset({"header", "validators"})


@dataclass(slots=True)
class ProfileConfig:
    head: int = 500
    spread: int = 1500
    region: str | None = None
    accept_threshold: float = 0.75
    other_threshold: float = 0.3
    agreement_bonus: float = 0.15
    cascade: bool = True
    """False runs every detector on every column (for evaluation)."""
    weights: dict[str, float] = field(
        default_factory=lambda: {"header": 1.0, "validators": 1.2, "gliner": 0.8, "nerd": 0.6, "llm": 1.0}
    )


STORED_SAMPLE_ROWS = 300
_NAMED_FORMATS = frozenset({TableFormat.PARQUET, TableFormat.JSON, TableFormat.JSONL})


@dataclass(slots=True)
class SheetSample:
    """A sheet's sampled data rows (header removed), its header guess and its columns."""

    format: TableFormat
    sheet: str | None
    guess: HeaderGuess
    rows: list[list[str]]
    columns: list[ColumnSample]
    context: TableContext
    rows_estimate: int | None
    encoding: str | None = None
    delimiter: str | None = None

    def stored(self, *, max_rows: int = STORED_SAMPLE_ROWS) -> TableSample:
        """The compact sample kept with a stored mapping (re-evaluation and previews run on it)."""
        return TableSample(headers=self.guess.names, rows=[r[: self.guess.width or None] for r in self.rows[:max_rows]])


def _sample(
    *,
    table_format: TableFormat,
    sheet: str | None,
    guess: HeaderGuess,
    rows: list[list[str]],
    has_header: bool,
    region: str | None,
    rows_estimate: int | None,
    encoding: str | None = None,
    delimiter: str | None = None,
) -> SheetSample:
    context = TableContext(headers=guess.names, has_header=has_header, preview_rows=rows[:20], region=region)
    return SheetSample(
        format=table_format,
        sheet=sheet,
        guess=guess,
        rows=rows,
        columns=build_columns(guess.names, rows),
        context=context,
        rows_estimate=rows_estimate,
        encoding=encoding,
        delimiter=delimiter,
    )


def sample_sheet(source: TableSource, *, sheet: str | None, config: ProfileConfig) -> SheetSample:
    """Sample one sheet, find its header, and transpose the data rows into columns."""
    raw = source.sample(sheet=sheet, head=config.head, spread=config.spread)
    guess = detect_header(raw.head, known_names=raw.names)
    return _sample(
        table_format=source.format,
        sheet=sheet,
        guess=guess,
        rows=data_rows(raw.head[guess.data_start_row :] + raw.spread, guess),
        has_header=bool(guess.header_rows) or raw.names is not None,
        region=config.region,
        rows_estimate=raw.rows_estimate,
        encoding=source.encoding,
        delimiter=source.delimiter,
    )


def sample_from_stored(mapping: TableMapping, sample: TableSample, *, region: str | None = None) -> SheetSample:
    """Rebuild a `SheetSample` from a stored mapping's sample, so it can be re-proposed without the file."""
    guess = HeaderGuess(
        header_rows=mapping.header_rows,
        data_start_row=mapping.data_start_row,
        names=sample.headers,
        width=len(sample.headers),
    )
    return _sample(
        table_format=mapping.format,
        sheet=mapping.sheet,
        guess=guess,
        rows=sample.rows,
        has_header=bool(mapping.header_rows) or mapping.format in _NAMED_FORMATS,
        region=region,
        rows_estimate=mapping.rows_estimate,
        encoding=mapping.encoding,
        delimiter=mapping.delimiter,
    )


def layout_of(mapping: TableMapping, *, width: int) -> TableSheetLayout:
    """Where one file's sheet keeps its header and data (stored per file; the mapping is shared)."""
    return TableSheetLayout(
        sheet=mapping.sheet,
        fingerprint=mapping.fingerprint,
        format=mapping.format,
        header_rows=mapping.header_rows,
        data_start_row=mapping.data_start_row,
        width=width,
        encoding=mapping.encoding,
        delimiter=mapping.delimiter,
        rows_estimate=mapping.rows_estimate,
    )


def fingerprint(names: list[str], *, has_header: bool) -> str:
    """Stable id of a header layout: files exported by the same system share it."""
    key = "|".join(normalize_header(n) for n in names) if has_header else f"#{len(names)}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _combine(per_detector: dict[str, ColumnScores], weights: dict[str, float], bonus: float) -> tuple[str, float]:
    voting = {name: s for name, s in per_detector.items() if s.scores}
    if not voting:
        return OTHER_FIELD, 0.0
    total = sum(weights.get(name, 1.0) for name in voting)
    combined: dict[str, float] = {}
    for name, scores in voting.items():
        for field_id, score in scores.scores.items():
            combined[field_id] = combined.get(field_id, 0.0) + weights.get(name, 1.0) * min(score, 1.0) / total
    best = max(combined, key=combined.__getitem__)
    agreeing = sum(1 for s in voting.values() if max(s.scores, key=s.scores.__getitem__) == best)
    confidence = combined[best] + (bonus * (agreeing - 1) if agreeing > 1 else 0.0)
    # A header claim whose cells fail their own validator is weak (e.g. a `phone` column of names).
    validators = per_detector.get("validators")
    if validators is not None and best in DISPROVABLE and validators.scores.get(best, 0.0) < 0.05:
        confidence *= 0.5
    return best, min(confidence, 1.0)


def _role(per_detector: dict[str, ColumnScores]) -> str | None:
    for name in ("llm", "header"):
        if (scores := per_detector.get(name)) and scores.role:
            return scores.role
    return None


def _pair_coordinates(decisions: list[ColumnDecision], columns: list[ColumnSample]) -> None:
    """Adjacent latitude/longitude columns become a pair.

    Next to a user-set one, a model column takes the other half; otherwise the
    column holding |x| > 90 is longitude, else the left one is latitude.
    """
    coordinate = ("location.latitude", "location.longitude")
    by_index = {c.index: c for c in columns}

    def wide(d: ColumnDecision) -> bool:
        return any(abs(x) > 90 for v in by_index[d.index].values[:300] if (x := parse_float(v)) is not None)

    def other(field_id: str) -> str:
        return coordinate[1 - coordinate.index(field_id)]

    for left, right in zip(decisions, decisions[1:], strict=False):
        if right.index != left.index + 1 or left.field_type not in coordinate or right.field_type not in coordinate:
            continue
        sources = (left.decision_source, right.decision_source)
        if sources == (MappingDecisionSource.USER, MappingDecisionSource.MODEL):
            right.field_type = other(left.field_type)
        elif sources == (MappingDecisionSource.MODEL, MappingDecisionSource.USER):
            left.field_type = other(right.field_type)
        elif (
            sources == (MappingDecisionSource.MODEL, MappingDecisionSource.MODEL)
            and left.field_type == right.field_type
        ):
            lat, lon = (right, left) if wide(left) and not wide(right) else (left, right)
            lat.field_type, lon.field_type = coordinate


def _apply_field(decision: ColumnDecision) -> None:
    spec = field_type(decision.field_type)
    decision.entity_type = spec.entity_type
    decision.attribute = spec.attribute
    decision.part = spec.part
    decision.selector_type = spec.ontology_selector_type
    decision.selector_subtype = SelectorSubtype(spec.selector_subtype) if spec.selector_subtype else None


def propose(
    sample: SheetSample,
    *,
    detectors: Sequence[Detector],
    locked: TableMapping | None = None,
    config: ProfileConfig | None = None,
) -> TableMapping:
    """The mapping for one sampled sheet."""
    config = config or ProfileConfig()
    columns = sample.columns
    user_columns = {
        c.index: c
        for c in (locked.columns if locked else [])
        if c.decision_source is MappingDecisionSource.USER and c.index < len(columns)
    }
    evidence: dict[int, dict[str, ColumnScores]] = {c.index: {} for c in columns}
    timings: dict[str, float] = {}
    hints: list[EdgeHint] = []

    def run(detector: Detector) -> None:
        started = time.perf_counter()
        for column, scores in zip(columns, detector.score(columns, context=sample.context), strict=True):
            evidence[column.index][detector.name] = scores
        timings[detector.name] = time.perf_counter() - started
        if hasattr(detector, "edge_hints"):
            hints.extend(detector.edge_hints())

    def undecided() -> bool:
        return any(
            _combine(evidence[c.index], config.weights, config.agreement_bonus)[1] < config.accept_threshold
            for c in columns
            if c.values and c.index not in user_columns
        )

    for detector in detectors:
        if not config.cascade or detector.name in CHEAP_DETECTORS or undecided():
            run(detector)

    region = region_hint(columns, sample.context)
    decisions: list[ColumnDecision] = []
    for column in columns:
        per_detector = evidence[column.index]
        if (user := user_columns.get(column.index)) is not None:
            decision = user.model_copy(update={"header": column.header})
        else:
            best, confidence = (
                _combine(per_detector, config.weights, config.agreement_bonus) if column.values else (OTHER_FIELD, 0.0)
            )
            if confidence < config.other_threshold:
                best = OTHER_FIELD
            decision = ColumnDecision(
                index=column.index,
                header=column.header,
                field_type=best,
                confidence=round(confidence, 3),
                role=_role(per_detector),
            )
        decision.profile = profile_column(column)
        decision.examples = column.preview(5)
        decision.evidence = [
            DetectorEvidence(detector=name, scores=s.top(), note=s.note)
            for name, s in per_detector.items()
            if s.scores or s.note
        ]
        decisions.append(decision)

    _pair_coordinates(decisions, columns)
    for decision, column in zip(decisions, columns, strict=True):
        _apply_field(decision)
        validators = evidence[column.index].get("validators")
        if decision.field_type == "selector.phone" and decision.transform is None and validators and validators.region:
            decision.transform = ColumnTransform(region_hint=validators.region)
        column_region = (
            decision.transform.region_hint if decision.transform and decision.transform.region_hint else region
        )
        decision.hit_rate, decision.failing_examples = hit_rate(
            decision.field_type, column.values, region=column_region
        )

    for decision in decisions:
        decision.slot = None  # recomputed: a retyped column may have left its slot
    slots, edges = build_slots(decisions, hints=hints, locked=locked)
    has_header = sample.context.has_header
    return TableMapping(
        fingerprint=fingerprint(sample.guess.names, has_header=has_header),
        format=sample.format,
        sheet=sample.sheet,
        header_rows=sample.guess.header_rows,
        data_start_row=sample.guess.data_start_row,
        rows_sampled=len(sample.rows),
        rows_estimate=sample.rows_estimate,
        encoding=sample.encoding,
        delimiter=sample.delimiter,
        columns=decisions,
        slots=slots,
        edges=edges,
        detectors=[f"{name} ({seconds * 1000:.0f} ms)" for name, seconds in timings.items()],
        is_verified=False,
    )


def profile_sheets(
    path: str | Path,
    *,
    detectors: Sequence[Detector],
    locked: list[TableMapping] | None = None,
    config: ProfileConfig | None = None,
    table_format: TableFormat | None = None,
) -> list[tuple[TableMapping, SheetSample]]:
    """One (mapping, sample) per non-empty sheet. A locked mapping applies to the sheet with the same name or layout.

    `table_format` overrides sniffing (stored files often have no extension).
    """
    config = config or ProfileConfig()
    source = TableSource(Path(path), table_format=table_format)
    out = []
    for sheet in source.sheets():
        sample = sample_sheet(source, sheet=sheet, config=config)
        if not sample.columns:
            continue
        layout = fingerprint(sample.guess.names, has_header=sample.context.has_header)
        match = next((m for m in locked or [] if m.sheet == sheet or m.fingerprint == layout), None)
        out.append((propose(sample, detectors=detectors, locked=match, config=config), sample))
    return out


def profile_table(
    path: str | Path,
    *,
    detectors: Sequence[Detector],
    locked: list[TableMapping] | None = None,
    config: ProfileConfig | None = None,
) -> list[TableMapping]:
    """One mapping per sheet (see `profile_sheets`)."""
    return [m for m, _ in profile_sheets(path, detectors=detectors, locked=locked, config=config)]
