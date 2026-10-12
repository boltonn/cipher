"""Table mapping: how a tabular file's columns map onto the ontology (column types, entity slots, edges).

Produced by `analytics/pytabular`, edited and verified by an analyst, consumed by the
(later) emit step. See docs/tabular-mapping.md.
"""

from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel, EnumStr, StrEnum
from cipher.schemas.graph.ontology import EntityType, SelectorSubtype, SelectorType

OTHER_FIELD = "other"


class TableFormat(StrEnum):
    CSV = "csv"
    PARQUET = "parquet"
    EXCEL = "excel"
    JSONL = "jsonl"
    JSON = "json"


class MappingDecisionSource(StrEnum):
    """Who set a column type, slot or edge. `user` values are locked against re-evaluation."""

    MODEL = "model"
    USER = "user"


class ColumnProfile(BaseModel):
    """Cheap per-column statistics over the sampled rows."""

    sampled: int = Field(default=0, description="Sampled cells, including empty ones")
    null_rate: float = Field(default=0.0)
    distinct_ratio: float = Field(default=0.0, description="Distinct non-empty values / non-empty values")
    mean_length: float = Field(default=0.0)
    max_length: int = Field(default=0)
    digit_ratio: float = Field(default=0.0)
    alpha_ratio: float = Field(default=0.0)
    script: str = Field(default="other", description="Dominant script of the column's letters")
    shapes: list[str] = Field(default_factory=list, description="Most common character shapes, e.g. `Aa+ Aa+`")
    multi_value_delimiter: str | None = Field(default=None, description="Set when cells look like delimited lists")


class DetectorEvidence(BaseModel):
    """One detector's view of one column: its top field-type scores."""

    detector: str
    scores: dict[str, float] = Field(default_factory=dict, description="Field type -> score in [0, 1]")
    note: str | None = Field(default=None)


class ColumnTransform(BaseModel):
    """How to turn a cell into a mention value at emit time."""

    region_hint: str | None = Field(default=None, description="ISO-3166 alpha-2 default region for phones")
    date_format: str | None = Field(default=None, description="strptime format when dates are ambiguous")
    split: str | None = Field(default=None, description="Delimiter for multi-value cells or `lat,lon` pairs")


class ColumnDecision(BaseModel):
    """The decided field type of one column, its ontology target, and the evidence behind it."""

    index: int
    header: str
    field_type: str = Field(default=OTHER_FIELD, description="Id from pytabular's field vocabulary")
    confidence: float = Field(default=0.0)
    entity_type: EntityType | None = Field(default=None)
    attribute: str | None = Field(default=None, description="Ontology attribute the value fills (or a part of it)")
    part: str | None = Field(default=None, description="Which part of a composite attribute, e.g. `given`, `latitude`")
    selector_type: SelectorType | None = Field(default=None)
    selector_subtype: SelectorSubtype | None = Field(default=None)
    role: str | None = Field(default=None, description="Who the column describes, e.g. `sender` (from header or LLM)")
    slot: str | None = Field(default=None, description="Name of the entity slot this column belongs to")
    transform: ColumnTransform | None = Field(default=None)
    decision_source: MappingDecisionSource = Field(default=MappingDecisionSource.MODEL)
    hit_rate: float | None = Field(default=None, description="Share of sampled cells that validate as `field_type`")
    examples: list[str] = Field(default_factory=list)
    failing_examples: list[str] = Field(default_factory=list, description="Sampled cells that fail validation")
    profile: ColumnProfile = Field(default_factory=ColumnProfile)
    evidence: list[DetectorEvidence] = Field(default_factory=list)


class EntitySlot(BaseModel):
    """One entity per row, built from a group of columns (e.g. `sender` = person[name, phone])."""

    name: str
    entity_type: EntityType
    columns: list[int] = Field(default_factory=list)
    decision_source: MappingDecisionSource = Field(default=MappingDecisionSource.MODEL)


class EdgeBinding(BaseModel):
    """A relationship emitted per row between two slots.

    `relationship_type` is a `RelationshipType` value, or a proposed verb the ontology
    doesn't have yet (`is_proposed_verb`) -- those need an ontology addition before emit.
    """

    src_slot: str
    dst_slot: str
    relationship_type: EnumStr
    is_proposed_verb: bool = Field(default=False)
    is_enabled: bool = Field(default=True, description="False: a user switched this edge off; it isn't emitted")
    date_column: int | None = Field(default=None, description="Column giving the edge's observed date")
    attribute_columns: list[int] = Field(default_factory=list, description="Columns copied onto edge attributes")
    decision_source: MappingDecisionSource = Field(default=MappingDecisionSource.MODEL)


class TableMapping(BaseModel):
    """The mapping of one sheet. Files sharing a header layout share a `fingerprint`."""

    fingerprint: str = Field(description="Hash of the normalized header list")
    format: TableFormat
    sheet: str | None = Field(default=None)
    header_rows: list[int] = Field(default_factory=list, description="0-based raw rows forming the header; [] = none")
    data_start_row: int = Field(default=0, description="0-based raw row where data begins")
    rows_sampled: int = Field(default=0)
    rows_estimate: int | None = Field(default=None)
    encoding: str | None = Field(default=None)
    delimiter: str | None = Field(default=None)
    columns: list[ColumnDecision] = Field(default_factory=list)
    slots: list[EntitySlot] = Field(default_factory=list)
    edges: list[EdgeBinding] = Field(default_factory=list)
    detectors: list[str] = Field(default_factory=list, description="Detectors that ran")
    is_verified: bool = Field(default=False)
    verified_by: str | None = Field(default=None)


class TableSample(BaseModel):
    """The sampled data rows a mapping was proposed from -- re-evaluation and previews run on it."""

    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class TableSheetLayout(BaseModel):
    """How one sheet of one file is laid out (stored on `file.table_sheets`); its mapping is found by fingerprint."""

    sheet: str | None = Field(default=None)
    fingerprint: str
    format: TableFormat
    header_rows: list[int] = Field(default_factory=list)
    data_start_row: int = Field(default=0)
    width: int = Field(default=0)
    encoding: str | None = Field(default=None)
    delimiter: str | None = Field(default=None)
    rows_estimate: int | None = Field(default=None)


class TableMappingStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    VERIFIED = "verified"


class TableMappingRecord(BaseModel):
    """A stored mapping: one per (dataset, header fingerprint), shared by every file with that layout."""

    id: str
    dataset_id: str
    fingerprint: str
    mapping: TableMapping
    sample: TableSample = Field(default_factory=TableSample)
    is_verified: bool = Field(default=False)
    verified_by: str | None = Field(default=None)
    date_verified: datetime | None = Field(default=None)
    date_created: datetime
    date_updated: datetime


class TableMappingFileStatus(StrEnum):
    """Where one file stands with this mapping's emit."""

    WAITING = "waiting"  # mapping not verified yet
    QUEUED = "queued"  # verified; `cipher emit-tables` hasn't written it yet
    EMITTED = "emitted"
    FAILED = "failed"


class TableMappingFile(BaseModel):
    """A file (sheet) that uses a mapping."""

    file_id: str
    sha256: str = Field(description="The table's id in `/tables/{sha256}`")
    filename: str
    sheet: str | None = Field(default=None)
    rows_estimate: int | None = Field(default=None)
    status: TableMappingFileStatus = Field(default=TableMappingFileStatus.WAITING)


class TableMappingSummary(BaseModel):
    """One row of the mappings list."""

    id: str
    dataset_id: str
    fingerprint: str
    sheet: str | None = Field(default=None)
    format: TableFormat
    headers: list[str] = Field(default_factory=list)
    column_count: int = Field(default=0)
    typed_column_count: int = Field(default=0, description="Columns not typed `other`")
    slot_count: int = Field(default=0)
    edge_count: int = Field(default=0)
    file_count: int = Field(default=0)
    rows_estimate: int = Field(default=0, description="Summed over the files using it")
    emitted_file_count: int = Field(default=0)
    status: TableMappingStatus = Field(default=TableMappingStatus.NEEDS_REVIEW)
    verified_by: str | None = Field(default=None)
    date_verified: datetime | None = Field(default=None)
    date_updated: datetime


class TableMappingDetail(TableMappingRecord):
    """A mapping with the files that use it."""

    files: list[TableMappingFile] = Field(default_factory=list)


class TableMappingUpdate(BaseModel):
    """An edited mapping. Parts with `decision_source = user` are locked; the rest is re-evaluated."""

    mapping: TableMapping


class FieldTypeOption(BaseModel):
    """One entry of the field vocabulary, for the column-type picker."""

    id: str
    label: str
    description: str
    group: str
    use: str
    entity_type: EntityType | None = Field(default=None)
    attribute: str | None = Field(default=None)
    selector_type: SelectorType | None = Field(default=None)
    needs_ontology: bool = Field(default=False)


class RelationshipVerbOption(BaseModel):
    """A verb an edge between slots can carry."""

    verb: EnumStr
    description: str
    is_proposed: bool = Field(default=False, description="Not in the ontology yet; such edges aren't emitted")


class TableView(BaseModel):
    """A table (by content hash) as the review page shows it: the file it was read from and each sheet's mapping."""

    sha256: str
    file_id: str
    filename: str
    dataset_id: str
    mappings: list[TableMappingDetail] = Field(default_factory=list)
