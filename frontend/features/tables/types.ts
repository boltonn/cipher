/** Table mappings -- mirrors `cipher.schemas.ingestion.table_mapping` (camelCase). See docs/tabular-mapping.md. */

export type TableFormat = "csv" | "parquet" | "excel" | "jsonl" | "json";
export type MappingDecisionSource = "model" | "user";
export type TableMappingStatus = "needsReview" | "verified";
export type TableMappingFileStatus = "waiting" | "queued" | "emitted" | "failed";
export type SlotEntityType = "person" | "organization" | "location" | "selector";

export interface ColumnProfile {
  sampled: number;
  nullRate: number;
  distinctRatio: number;
  meanLength: number;
  maxLength: number;
  script: string;
  shapes: string[];
  multiValueDelimiter: string | null;
}

export interface DetectorEvidence {
  detector: string;
  scores: Record<string, number>;
  note: string | null;
}

export interface ColumnTransform {
  regionHint: string | null;
  dateFormat: string | null;
  split: string | null;
}

export interface ColumnDecision {
  index: number;
  header: string;
  fieldType: string;
  confidence: number;
  entityType: SlotEntityType | null;
  attribute: string | null;
  part: string | null;
  selectorType: string | null;
  selectorSubtype: string | null;
  role: string | null;
  slot: string | null;
  transform: ColumnTransform | null;
  decisionSource: MappingDecisionSource;
  hitRate: number | null;
  examples: string[];
  failingExamples: string[];
  profile: ColumnProfile;
  evidence: DetectorEvidence[];
}

export interface EntitySlot {
  name: string;
  entityType: SlotEntityType;
  columns: number[];
  decisionSource: MappingDecisionSource;
}

export interface EdgeBinding {
  srcSlot: string;
  dstSlot: string;
  relationshipType: string;
  isProposedVerb: boolean;
  isEnabled: boolean;
  dateColumn: number | null;
  attributeColumns: number[];
  decisionSource: MappingDecisionSource;
}

export interface TableMapping {
  fingerprint: string;
  format: TableFormat;
  sheet: string | null;
  headerRows: number[];
  dataStartRow: number;
  rowsSampled: number;
  rowsEstimate: number | null;
  encoding: string | null;
  delimiter: string | null;
  columns: ColumnDecision[];
  slots: EntitySlot[];
  edges: EdgeBinding[];
  detectors: string[];
  isVerified: boolean;
  verifiedBy: string | null;
}

export interface TableSample {
  headers: string[];
  rows: string[][];
}

export interface TableMappingFile {
  fileId: string;
  /** The table's id in `/tables/[sha256]`. */
  sha256: string;
  filename: string;
  sheet: string | null;
  rowsEstimate: number | null;
  status: TableMappingFileStatus;
}

export interface TableMappingDetail {
  id: string;
  datasetId: string;
  fingerprint: string;
  mapping: TableMapping;
  sample: TableSample;
  isVerified: boolean;
  verifiedBy: string | null;
  dateVerified: string | null;
  dateCreated: string;
  dateUpdated: string;
  files: TableMappingFile[];
}

export interface TableMappingSummary {
  id: string;
  datasetId: string;
  fingerprint: string;
  sheet: string | null;
  format: TableFormat;
  headers: string[];
  columnCount: number;
  typedColumnCount: number;
  slotCount: number;
  edgeCount: number;
  fileCount: number;
  rowsEstimate: number;
  emittedFileCount: number;
  status: TableMappingStatus;
  verifiedBy: string | null;
  dateVerified: string | null;
  dateUpdated: string;
}

/** A table by content hash, as its review page shows it. */
export interface TableView {
  sha256: string;
  fileId: string;
  filename: string;
  datasetId: string;
  mappings: TableMappingDetail[];
}

export interface FieldTypeOption {
  id: string;
  label: string;
  description: string;
  group: string;
  use: string;
  entityType: SlotEntityType | null;
  attribute: string | null;
  selectorType: string | null;
  needsOntology: boolean;
}

export interface RelationshipVerbOption {
  verb: string;
  description: string;
  isProposed: boolean;
}

export const OTHER_FIELD = "other";
