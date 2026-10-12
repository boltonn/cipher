"""Open a tabular file without loading it: sniff the format, encoding and dialect, sample rows, stream batches.

Every reader yields rows as `list[str]` (empty string for a missing cell), so the
profiler never sees typed values -- type detection is the profiler's job, not the
parser's. A sample is the first `head` rows plus rows spread across the rest of the
file; big text files are sampled by seeking to byte offsets rather than reading them
end to end.
"""

import codecs
import csv
import io
import json
import random
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import BinaryIO

from charset_normalizer import from_bytes

from cipher.schemas.ingestion.table_mapping import TableFormat

SNIFF_BYTES = 1 << 20
SEEK_SAMPLE_MIN_BYTES = 64 << 20
_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xlsb", ".xls", ".ods"}
_DELIMITERS = ",;\t|"
LEGACY_ENCODINGS = (
    "cp1251",
    "koi8_r",
    "cp1256",
    "cp1252",
    "gb18030",
    "big5",
    "shift_jis",
    "euc_kr",
    "cp1255",
    "cp1253",
    "cp1254",
)
"""Codepages seen in exports from the target languages; charset-normalizer picks among these first."""


@dataclass(slots=True)
class RawSample:
    """Sampled raw rows of one sheet, before header detection."""

    head: list[list[str]]
    spread: list[list[str]] = field(default_factory=list)
    rows_estimate: int | None = None
    names: list[str] | None = None
    """Column names when the format carries them (parquet, json), so no header detection is needed."""


def sniff_format(path: Path) -> TableFormat:
    """Format from the extension, falling back to magic bytes."""
    suffix = path.suffix.lower()
    if suffix in _EXCEL_SUFFIXES:
        return TableFormat.EXCEL
    if suffix == ".parquet":
        return TableFormat.PARQUET
    if suffix in {".jsonl", ".ndjson"}:
        return TableFormat.JSONL
    if suffix == ".json":
        return TableFormat.JSON
    with path.open("rb") as handle:
        magic = handle.read(8)
    if magic.startswith(b"PAR1"):
        return TableFormat.PARQUET
    if magic.startswith(b"PK") or magic.startswith(b"\xd0\xcf\x11\xe0"):
        return TableFormat.EXCEL
    return TableFormat.CSV


def sniff_encoding(raw: bytes) -> str:
    """Python codec name for a byte sample (BOM first, then charset-normalizer, else utf-8)."""
    for bom, name in ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if raw.startswith(bom):
            return name
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError as exc:
        if exc.start > len(raw) - 4:
            return "utf-8"  # the sample cut a multi-byte character in half
    best = from_bytes(raw, cp_isolation=list(LEGACY_ENCODINGS)).best() or from_bytes(raw).best()
    return best.encoding if best else "utf-8"


def sniff_delimiter(text: str) -> str:
    """The delimiter giving the most consistent field count over the first lines."""
    lines = [line for line in text.splitlines()[:50] if line.strip()]
    if not lines:
        return ","
    try:
        return csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=_DELIMITERS).delimiter
    except csv.Error:
        pass

    def consistency(delim: str) -> tuple[float, float]:
        counts = [len(row) for row in csv.reader(lines, delimiter=delim)]
        modal = max(set(counts), key=counts.count)
        return (counts.count(modal) / len(counts) if modal > 1 else 0.0, modal)

    return max(_DELIMITERS, key=consistency)


def cell_text(value: object) -> str:
    """A typed cell (Excel / parquet) as the text a person would read; integral floats lose `.0`."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value != value:
            return ""
        return str(int(value)) if value.is_integer() and abs(value) < 1e16 else repr(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ") if value.time() != time(0) else value.date().isoformat()
    if isinstance(value, date | time):
        return value.isoformat()
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value).strip()


def flatten_record(record: dict, prefix: str = "") -> dict[str, str]:
    """Nested JSON object -> `{"a.b": "text"}`; lists stay JSON text."""
    flat: dict[str, str] = {}
    for key, value in record.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten_record(value, prefix=f"{name}."))
        else:
            flat[name] = cell_text(value)
    return flat


class TableSource:
    """One tabular file: its sheets, a per-sheet raw sample, and streamed row batches."""

    def __init__(self, path: Path, *, table_format: TableFormat | None = None):
        self.path = path
        self.format = table_format or sniff_format(path)
        self.encoding: str | None = None
        self.delimiter: str | None = None
        if self.format is TableFormat.CSV:
            with path.open("rb") as handle:
                raw = handle.read(SNIFF_BYTES)
            self.encoding = sniff_encoding(raw)
            self.delimiter = (
                "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(raw.decode(self.encoding, errors="replace"))
            )

    def sheets(self) -> list[str | None]:
        """Sheet names (Excel) or `[None]` for single-table formats."""
        if self.format is not TableFormat.EXCEL:
            return [None]
        from python_calamine import CalamineWorkbook

        return list(CalamineWorkbook.from_path(str(self.path)).sheet_names)

    def sample(self, *, sheet: str | None = None, head: int = 500, spread: int = 1500, seed: int = 0) -> RawSample:
        """The first `head` rows plus up to `spread` rows from across the rest of the sheet."""
        rng = random.Random(seed)
        match self.format:
            case TableFormat.CSV:
                return self._sample_csv(head=head, spread=spread, rng=rng)
            case TableFormat.EXCEL:
                return self._sample_excel(sheet=sheet, head=head, spread=spread, rng=rng)
            case TableFormat.PARQUET:
                return self._sample_parquet(head=head, spread=spread, rng=rng)
            case TableFormat.JSONL | TableFormat.JSON:
                return self._sample_json(head=head, spread=spread, rng=rng)

    def iter_rows(self, *, sheet: str | None = None) -> Iterator[list[str]]:
        """Every raw row, streamed (header rows included for csv/excel, excluded for parquet/json)."""
        match self.format:
            case TableFormat.CSV:
                with self._text() as text:
                    yield from csv.reader(text, delimiter=self.delimiter or ",")
            case TableFormat.EXCEL:
                yield from (list(map(cell_text, row)) for row in self._excel_sheet(sheet).iter_rows())
            case TableFormat.PARQUET:
                import pyarrow.parquet as pq

                for batch in pq.ParquetFile(self.path).iter_batches(batch_size=10_000):
                    columns = [column.to_pylist() for column in batch.columns]
                    yield from ([cell_text(v) for v in row] for row in zip(*columns, strict=True))
            case TableFormat.JSONL | TableFormat.JSON:
                names: list[str] | None = None
                for record in self._json_records():
                    flat = flatten_record(record)
                    names = names or list(flat)
                    yield [flat.get(name, "") for name in names]

    def iter_batches(self, *, sheet: str | None = None, data_start_row: int = 0, size: int = 50_000):
        """Data rows as polars DataFrames of strings -- the emit-time full scan.

        UTF-8 csv goes straight through polars' streaming reader; anything else is
        streamed row by row into frames of `size`.
        """
        import polars as pl

        if self.format is TableFormat.CSV and self.encoding in {"utf-8", "utf-8-sig", "ascii"}:
            lazy = pl.scan_csv(
                self.path,
                has_header=False,
                separator=self.delimiter or ",",
                skip_rows=data_start_row,
                infer_schema=False,
                encoding="utf8-lossy",
                truncate_ragged_lines=True,
                ignore_errors=True,
                missing_utf8_is_empty_string=True,
            )
            yield from lazy.collect_batches(chunk_size=size)
            return
        skip = data_start_row if self.format in {TableFormat.CSV, TableFormat.EXCEL} else 0
        batch: list[list[str]] = []
        for i, row in enumerate(self.iter_rows(sheet=sheet)):
            if i < skip:
                continue
            batch.append(row)
            if len(batch) >= size:
                yield _frame(batch)
                batch = []
        if batch:
            yield _frame(batch)

    def _text(self) -> io.TextIOWrapper:
        return io.TextIOWrapper(self.path.open("rb"), encoding=self.encoding or "utf-8", errors="replace", newline="")

    def _sample_csv(self, *, head: int, spread: int, rng: random.Random) -> RawSample:
        size = self.path.stat().st_size
        seekable = size >= SEEK_SAMPLE_MIN_BYTES and not (self.encoding or "").startswith("utf-16")
        if not seekable:
            return _reservoir(self.iter_rows(), head=head, spread=spread, rng=rng)
        rows: list[list[str]] = []
        with self._text() as text:
            for row in csv.reader(text, delimiter=self.delimiter or ","):
                rows.append(row)
                if len(rows) >= head:
                    break
        row_bytes = sum(len((self.delimiter or ",").join(r).encode("utf-8")) + 1 for r in rows) / max(len(rows), 1)
        return RawSample(
            head=rows, spread=self._seek_rows(spread=spread, rng=rng), rows_estimate=int(size / max(row_bytes, 1))
        )

    def _seek_rows(self, *, spread: int, rng: random.Random, per_seek: int = 25) -> list[list[str]]:
        """Rows read after random byte offsets (each resynced to the next line start)."""
        size = self.path.stat().st_size
        rows: list[list[str]] = []
        with self.path.open("rb") as handle:
            for offset in sorted(rng.randrange(SNIFF_BYTES, size) for _ in range(max(spread // per_seek, 1))):
                handle.seek(offset)
                handle.readline()
                chunk = b"".join(handle.readline() for _ in range(per_seek))
                text = chunk.decode(self.encoding or "utf-8", errors="replace")
                rows.extend(csv.reader(io.StringIO(text), delimiter=self.delimiter or ","))
        return rows[:spread]

    def _excel_sheet(self, sheet: str | None):
        from python_calamine import CalamineWorkbook

        workbook = CalamineWorkbook.from_path(str(self.path))
        return workbook.get_sheet_by_name(sheet) if sheet else workbook.get_sheet_by_index(0)

    def _sample_excel(self, *, sheet: str | None, head: int, spread: int, rng: random.Random) -> RawSample:
        return _reservoir(self.iter_rows(sheet=sheet), head=head, spread=spread, rng=rng)

    def _sample_parquet(self, *, head: int, spread: int, rng: random.Random) -> RawSample:
        import pyarrow.parquet as pq

        parquet = pq.ParquetFile(self.path)
        names = parquet.schema_arrow.names

        def rows_of(table) -> list[list[str]]:
            columns = [column.to_pylist() for column in table.columns]
            return [[cell_text(v) for v in row] for row in zip(*columns, strict=True)]

        first = next(parquet.iter_batches(batch_size=head), None)
        rows = rows_of(first) if first is not None else []
        groups = list(range(1, parquet.num_row_groups))
        picked: list[list[str]] = []
        for group in rng.sample(groups, min(len(groups), 8)):
            table = parquet.read_row_group(group)
            take = sorted(rng.sample(range(table.num_rows), min(table.num_rows, spread // 8 or 1)))
            picked.extend(rows_of(table.take(take)))
        return RawSample(head=rows, spread=picked[:spread], rows_estimate=parquet.metadata.num_rows, names=names)

    def _json_records(self) -> Iterator[dict]:
        if self.format is TableFormat.JSONL:
            with self.path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.strip():
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(record, dict):
                            yield record
            return
        parsed = json.loads(self.path.read_text(encoding="utf-8", errors="replace"))
        records = (
            parsed if isinstance(parsed, list) else next((v for v in parsed.values() if isinstance(v, list)), [parsed])
        )
        yield from (r for r in records if isinstance(r, dict))

    def _sample_json(self, *, head: int, spread: int, rng: random.Random) -> RawSample:
        flat_head: list[dict[str, str]] = []
        reservoir: list[dict[str, str]] = []
        seen = 0
        for i, record in enumerate(self._json_records()):
            if i < head:
                flat_head.append(flatten_record(record))
                continue
            seen += 1
            if len(reservoir) < spread:
                reservoir.append(flatten_record(record))
            elif (j := rng.randrange(seen)) < spread:
                reservoir[j] = flatten_record(record)
        names = list(dict.fromkeys(k for record in [*flat_head, *reservoir] for k in record))

        def as_rows(records: list[dict[str, str]]) -> list[list[str]]:
            return [[r.get(name, "") for name in names] for r in records]

        return RawSample(
            head=as_rows(flat_head), spread=as_rows(reservoir), rows_estimate=len(flat_head) + seen, names=names
        )


def _reservoir(rows: Iterator[list[str]], *, head: int, spread: int, rng: random.Random) -> RawSample:
    """First `head` rows plus a uniform reservoir of `spread` over the rest, in one streamed pass."""
    first: list[list[str]] = []
    reservoir: list[list[str]] = []
    seen = 0
    for row in rows:
        if len(first) < head:
            first.append(row)
            continue
        seen += 1
        if len(reservoir) < spread:
            reservoir.append(row)
        elif (j := rng.randrange(seen)) < spread:
            reservoir[j] = row
    return RawSample(head=first, spread=reservoir, rows_estimate=len(first) + seen)


def _frame(rows: list[list[str]]):
    import polars as pl

    width = max(len(r) for r in rows)
    padded = [r + [""] * (width - len(r)) for r in rows]
    return pl.DataFrame(padded, schema=[f"column_{i + 1}" for i in range(width)], orient="row")


def open_table(path: str | Path) -> TableSource:
    """A `TableSource` for `path` (format, encoding and delimiter sniffed)."""
    return TableSource(Path(path))


def spooled_copy(source: BinaryIO, *, suffix: str) -> Path:
    """Stream an upload to a temp file so the readers can seek it (never held in memory)."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        shutil.copyfileobj(source, handle, length=1 << 20)
    return Path(handle.name)
