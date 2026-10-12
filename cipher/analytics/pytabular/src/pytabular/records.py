"""Read a mapped row into per-slot records: composed names, normalized attributes, validated selectors.

Pure (no database): `cipher emit-tables` turns the records into mentions and edges.
Values that fail validation for their column's type are dropped and counted, never
emitted as-is.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache

from cipher.schemas.graph.ontology import EntityType, SelectorSubtype, SelectorType
from cipher.schemas.ingestion.table_mapping import ColumnDecision, EdgeBinding, TableMapping
from pytabular.detectors.validators import gazetteer, parse_date
from pytabular.fields import FieldUse, demonyms, field_type, normalize_header
from pytabular.profile import is_null

_NAME_ORDER = ("person.given_name", "person.patronymic", "person.surname")
_ADDRESS_ORDER = (
    "location.street",
    "location.house_number",
    "location.unit",
    "location.postal_code",
    "location.city",
    "location.admin_area",
    "location.country",
)
_PLACE_PREFERENCE = ("location.place_name", "location.city", "location.admin_area", "location.country")


@dataclass(frozen=True, slots=True)
class SelectorValue:
    selector_type: SelectorType
    raw: str
    normalized: str
    selector_subtype: SelectorSubtype | None = None
    region_hint: str | None = None


@dataclass(frozen=True, slots=True)
class SlotRecord:
    """One slot's entity on one row. `surface` keeps the cell text each attribute came from."""

    slot: str
    entity_type: EntityType
    name: str | None = None
    address: str | None = None
    coordinate: tuple[float, float] | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    selectors: tuple[SelectorValue, ...] = ()
    surface: tuple[tuple[str, str], ...] = ()

    @property
    def is_empty(self) -> bool:
        """Nothing in this slot on this row (all its cells empty or invalid)."""
        return not (self.name or self.address or self.coordinate or self.selectors or self.attributes)

    def key(self) -> tuple:
        """Identity within a file: identical records collapse into one mention set."""
        return (self.slot, self.name, self.address, self.coordinate, self.attributes, self.selectors)


@dataclass(slots=True)
class RowRecords:
    slots: list[SlotRecord]
    date: datetime | None = None
    duration_seconds: float | None = None
    edge_cells: dict[int, str] = field(default_factory=dict)
    """Edge-attribute column index -> cell; each edge reads only its own columns (`RowExtractor.edge_attributes`)."""


@lru_cache(maxsize=200_000)
def normalize_selector_value(
    value: str, selector_type: SelectorType, region: str | None
) -> tuple[str, SelectorSubtype | None] | None:
    """(normalized, subtype) when the cell validates as `selector_type` (pyselectors `resolve_cell`), else None."""
    from pyselectors import resolve_cell

    span = resolve_cell(value, selector_type, region=region)
    return (span.normalized_value, span.selector_subtype) if span else None


@lru_cache(maxsize=50_000)
def nationality_code(value: str) -> str | None:
    """`Russian` / `РФ` / `Россия` -> `RU`."""
    key = normalize_header(value)
    if code := demonyms().get(key):
        return code
    countries = [p for p in gazetteer().candidates(value) if p.kind.value == "country" and p.country_code]
    return countries[0].country_code if len(countries) == 1 else None


def parse_coordinate(latitude: str | None, longitude: str | None, pair: str | None) -> tuple[float, float] | None:
    """Latitude + longitude cells, or a pair cell (pyselectors' cell parsers), in range and not (0, 0)."""
    from pyselectors import parse_coordinate_cell, parse_degrees

    if pair:
        span = parse_coordinate_cell(pair)
        return (span.latitude, span.longitude) if span else None
    if not (latitude and longitude):
        return None
    lat, lon = parse_degrees(latitude), parse_degrees(longitude)
    if lat is None or lon is None:
        return None
    lat_value, lon_value = lat[0], lon[0]
    if -90 <= lat_value <= 90 and -180 <= lon_value <= 180 and (lat_value, lon_value) != (0, 0):
        return round(lat_value, 6), round(lon_value, 6)
    return None


def parse_edge_date(value: str, field_id: str) -> datetime | None:
    """A row's date / datetime / epoch cell as an aware datetime."""
    text = value.strip()
    if field_id == "time.epoch" and text.lstrip("-").isdigit():
        number = int(text)
        return datetime.fromtimestamp(number / 1000 if number > 10**11 else number, tz=UTC)
    parsed, _ = parse_date(text)
    return parsed.replace(tzinfo=UTC) if parsed else None


_ROW_TIME_FIELDS = ("time.datetime", "time.epoch", "time.date")


def parse_duration_seconds(value: str) -> float | None:
    """`180` / `180.5` (seconds), `3:00` (m:ss) or `1:03:00` (h:mm:ss) -> seconds."""
    text = value.strip().replace(",", ".")
    if ":" in text:
        parts = text.split(":")
        if len(parts) > 3 or not all(p.isdigit() for p in parts):
            return None
        return float(sum(int(p) * 60**i for i, p in enumerate(reversed(parts))))
    try:
        seconds = float(text)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


class RowExtractor:
    """Pre-plans a verified mapping once, then reads rows into `RowRecords`."""

    def __init__(self, mapping: TableMapping):
        self.mapping = mapping
        self.columns = {c.index: c for c in mapping.columns}
        self.rejected: Counter[str] = Counter()
        edge_columns = {i for e in mapping.edges for i in (*e.attribute_columns, e.date_column) if i is not None}
        self._edge_attribute_columns = sorted(
            i for i in edge_columns if field_type(self.columns[i].field_type).use is FieldUse.EDGE_ATTRIBUTE
        )
        # The edges' date column, else the first time column (a GPS log has a location slot but no edges).
        self._date_column = next((e.date_column for e in mapping.edges if e.date_column is not None), None)
        if self._date_column is None:
            times = {c.field_type: c.index for c in reversed(mapping.columns) if c.field_type in _ROW_TIME_FIELDS}
            self._date_column = next((times[f] for f in _ROW_TIME_FIELDS if f in times), None)
        self._duration_column = next((c.index for c in mapping.columns if c.field_type == "time.duration"), None)

    def extract(self, row: list[str]) -> RowRecords:
        """One row's slot records, date, duration and edge-attribute cells."""
        records = []
        for slot in self.mapping.slots:
            record = self._slot(
                slot.name, slot.entity_type, [self.columns[i] for i in slot.columns if i in self.columns], row
            )
            if not record.is_empty:
                records.append(record)
        out = RowRecords(slots=records)
        if self._date_column is not None and (cell := _cell(row, self._date_column)):
            out.date = parse_edge_date(cell, self.columns[self._date_column].field_type)
        if self._duration_column is not None and (cell := _cell(row, self._duration_column)):
            out.duration_seconds = parse_duration_seconds(cell)
        for index in self._edge_attribute_columns:
            if cell := _cell(row, index):
                out.edge_cells[index] = cell[:200]
        return out

    def edge_attributes(self, edge: EdgeBinding, out: RowRecords) -> dict[str, str]:
        """This edge's attributes on one row (`role` for employment, `amount` / `duration` / ... otherwise)."""
        return {
            _attribute_key(self.columns[i]): out.edge_cells[i] for i in edge.attribute_columns if i in out.edge_cells
        }

    def _slot(self, name: str, entity_type: EntityType, columns: list[ColumnDecision], row: list[str]) -> SlotRecord:
        values: dict[str, str] = {}
        selectors: list[SelectorValue] = []
        surface: dict[str, str] = {}
        attributes: dict[str, str] = {}
        for column in columns:
            cell = _cell(row, column.index)
            if not cell:
                continue
            spec = field_type(column.field_type)
            if spec.selector_type:
                selector_type = spec.ontology_selector_type
                if selector_type is None:
                    continue
                region = column.transform.region_hint if column.transform else None
                for raw in _split(cell, column):
                    hit = normalize_selector_value(raw, selector_type, region)
                    if hit is None:
                        self.rejected[column.field_type] += 1
                        continue
                    selectors.append(
                        SelectorValue(
                            selector_type=selector_type,
                            raw=raw,
                            normalized=hit[0],
                            selector_subtype=hit[1],
                            region_hint=region,
                        )
                    )
                continue
            values.setdefault(column.field_type, cell)
            match column.field_type:
                case "person.date_of_birth":
                    parsed, _ = parse_date(cell)
                    if parsed is None:
                        self.rejected[column.field_type] += 1
                    else:
                        attributes["date_of_birth"], surface["date_of_birth"] = parsed.date().isoformat(), cell
                case "person.nationality":
                    if code := nationality_code(cell):
                        attributes["nationality"], surface["nationality"] = code, cell
                    else:
                        self.rejected[column.field_type] += 1

        record_name: str | None = None
        address: str | None = None
        coordinate: tuple[float, float] | None = None
        if entity_type is EntityType.PERSON:
            record_name = (
                values.get("person.full_name") or " ".join(values[f] for f in _NAME_ORDER if f in values) or None
            )
        elif entity_type is EntityType.ORGANIZATION:
            record_name = values.get("organization.name")
        elif entity_type is EntityType.LOCATION:
            parts = [values[f] for f in _ADDRESS_ORDER if f in values]
            has_street = any(f in values for f in _ADDRESS_ORDER[:4])
            address = values.get("location.address") or (", ".join(parts) if has_street else None)
            record_name = None if address else next((values[f] for f in _PLACE_PREFERENCE if f in values), None)
            coordinate = parse_coordinate(
                values.get("location.latitude"), values.get("location.longitude"), values.get("location.coordinate")
            )
            if coordinate:
                surface["coordinate"] = (
                    values.get("location.coordinate")
                    or f"{values.get('location.latitude')}, {values.get('location.longitude')}"
                )
        if record_name:
            surface["name"] = record_name
        if address:
            surface["address"] = address
        return SlotRecord(
            slot=name,
            entity_type=entity_type,
            name=record_name,
            address=address,
            coordinate=coordinate,
            attributes=tuple(sorted(attributes.items())),
            selectors=tuple(dict.fromkeys(selectors)),
            surface=tuple(sorted(surface.items())),
        )


def _cell(row: list[str], index: int) -> str | None:
    value = row[index].strip() if index < len(row) else ""
    return None if is_null(value) else value


def _split(cell: str, column: ColumnDecision) -> list[str]:
    delimiter = (column.transform.split if column.transform else None) or column.profile.multi_value_delimiter
    parts = cell.split(delimiter) if delimiter else [cell]
    return [p.strip() for p in parts if p.strip()]


def _attribute_key(column: ColumnDecision) -> str:
    """`edge.amount` -> `amount`; free categories keep their header (`status`)."""
    if column.field_type in ("other.category", "other"):
        return normalize_header(column.header).replace(" ", "_") or f"column_{column.index}"
    if column.field_type == "person.occupation":
        return "role"  # the key `extract-signatures` puts on employed_by edges
    return column.field_type.split(".", 1)[-1]


def edge_is_emittable(edge: EdgeBinding) -> bool:
    """Enabled and using an ontology verb."""
    return edge.is_enabled and not edge.is_proposed_verb
