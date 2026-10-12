"""Score detector combinations against labelled tables: accuracy, macro-F1 and time per column."""

import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from cipher.schemas.ingestion.table_mapping import OTHER_FIELD
from pytabular.decide import ProfileConfig, profile_table
from pytabular.detectors import Detector


@dataclass(slots=True)
class LabelledTable:
    path: Path
    labels: dict[int | str, str]
    """Column index or header text -> expected field type."""
    sheet: str | None = None


@dataclass(slots=True)
class ComboResult:
    combo: str
    correct: int = 0
    total: int = 0
    seconds: float = 0.0
    confusion: Counter = field(default_factory=Counter)
    """(expected, predicted) -> count, mistakes only."""
    true_positive: Counter = field(default_factory=Counter)
    predicted: Counter = field(default_factory=Counter)
    expected: Counter = field(default_factory=Counter)

    @property
    def accuracy(self) -> float:
        """Share of labelled columns typed correctly."""
        return self.correct / self.total if self.total else 0.0

    @property
    def macro_f1(self) -> float:
        """F1 averaged over the expected field types, so rare types count as much as common ones."""
        scores = []
        for label in self.expected:
            precision = self.true_positive[label] / self.predicted[label] if self.predicted[label] else 0.0
            recall = self.true_positive[label] / self.expected[label]
            scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
        return sum(scores) / len(scores) if scores else 0.0

    @property
    def ms_per_column(self) -> float:
        """Wall time per labelled column, reading included."""
        return 1000 * self.seconds / self.total if self.total else 0.0


def load_labels(path: Path) -> list[LabelledTable]:
    """`labels.yaml`: a list of `{path, sheet?, columns: {header or "#index": field_type}}`."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    tables = []
    for entry in raw:
        labels = {int(k[1:]) if str(k).startswith("#") else str(k): v for k, v in entry["columns"].items()}
        table_path = Path(entry["path"])
        tables.append(
            LabelledTable(
                path=table_path if table_path.is_absolute() else path.parent / table_path,
                labels=labels,
                sheet=entry.get("sheet"),
            )
        )
    return tables


def evaluate(
    tables: Sequence[LabelledTable], combos: dict[str, Sequence[Detector]], *, config: ProfileConfig | None = None
) -> list[ComboResult]:
    """Run every detector combination over every table."""
    results = []
    for combo, detectors in combos.items():
        result = ComboResult(combo=combo)
        for table in tables:
            started = time.perf_counter()
            mappings = profile_table(table.path, detectors=detectors, config=config)
            result.seconds += time.perf_counter() - started
            mapping = next((m for m in mappings if m.sheet == table.sheet), mappings[0] if mappings else None)
            if mapping is None:
                continue
            for column in mapping.columns:
                expected = table.labels.get(column.index, table.labels.get(column.header))
                if expected is None:
                    continue
                predicted = column.field_type or OTHER_FIELD
                result.total += 1
                result.expected[expected] += 1
                result.predicted[predicted] += 1
                if predicted == expected:
                    result.correct += 1
                    result.true_positive[expected] += 1
                else:
                    result.confusion[(expected, predicted)] += 1
        results.append(result)
    return results


def report(results: Sequence[ComboResult], *, mistakes: int = 8) -> str:
    """A plain-text comparison table plus each combination's most common mistakes."""
    lines = [f"{'detectors':<40} {'columns':>8} {'accuracy':>9} {'macro-F1':>9} {'ms/column':>10}"]
    for r in results:
        lines.append(f"{r.combo:<40} {r.total:>8} {r.accuracy:>9.3f} {r.macro_f1:>9.3f} {r.ms_per_column:>10.1f}")
    for r in results:
        if r.confusion:
            lines.append(f"\n{r.combo} -- most common mistakes (expected -> predicted):")
            lines.extend(f"  {n:>4}  {e} -> {p}" for (e, p), n in r.confusion.most_common(mistakes))
    return "\n".join(lines)
