import { SortOrderType } from "@/types/common";
import { z } from "zod";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const DatasetSortField = {
  Name: "name",
  DateCreated: "dateCreated",
  DateLastUpdated: "dateLastUpdated",
  FileCount: "fileCount",
  TotalSizeBytes: "totalSizeBytes",
  FiletypeCount: "filetypeCount",
} as const;

export type DatasetSortFieldType =
  (typeof DatasetSortField)[keyof typeof DatasetSortField];

export interface Dataset {
  id: string;
  name: string;
  description: string;
  dateCreated: string;
  dateLastUpdated: string;
  /** Listed (locked) for users who aren't members. */
  isDiscoverable: boolean;
  /** When staging first completed (files loaded + typed); null until then. */
  dateStaged: string | null;
  /** Whether you can open, triage and search it; false = discoverable only (locked). */
  hasAccess: boolean;
}

export interface DatasetSummary extends Dataset {
  fileCount: number;
  totalSizeBytes: number;
  filetypeCount: number;
  /** Users with explicit membership (admins see every dataset regardless). */
  memberCount: number;
}

export const DatasetCreateSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  isDiscoverable: z.boolean().optional(),
});

export type DatasetCreate = z.infer<typeof DatasetCreateSchema>;

export const DatasetUpdateSchema = z.object({
  name: z.string().min(1, "Name is required").optional(),
  description: z.string().optional(),
  isDiscoverable: z.boolean().optional(),
});

export type DatasetUpdate = z.infer<typeof DatasetUpdateSchema>;

export interface DatasetRequest {
  query?: string;
  dateCreatedFrom?: string;
  dateCreatedTo?: string;
  dateLastUpdatedFrom?: string;
  dateLastUpdatedTo?: string;
  sortBy?: DatasetSortFieldType;
  sortOrder?: SortOrderType;
  limit?: number;
  page?: number;
}

export interface FiletypeBreakdownItem {
  filetype: string;
  count: number;
}

export interface LoadHistogramBucket {
  dateBucket: string;
  count: number;
}

export type HistogramGranularityType = "day" | "week" | "month";

export interface DatasetStatsRequest {
  dateFrom?: string;
  dateTo?: string;
  granularity?: HistogramGranularityType;
  filetype?: string;
  filetypeGroup?: string;
}

export interface DatasetStatsResponse {
  totalFiles: number;
  totalSizeBytes: number;
  byFiletype: FiletypeBreakdownItem[];
  byFiletypeGroup: FiletypeBreakdownItem[];
  loadedOverTime: LoadHistogramBucket[];
}

export type ProcessingStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "skipped";

/** Per-analytic progress for one dataset (see backend `DatasetEnrichmentProgress`). */
export interface EnrichmentProgress {
  datasetId: string;
  enrichmentType: string;
  counts: Partial<Record<ProcessingStatus, number>>;
  total: number;
  completed: number;
  /** 0..1, share of rows completed. */
  progress: number;
  /** Per-pass progress when the analytic runs in passes (event extraction: calendar, gate, LLM). */
  stages: EnrichmentStageProgress[];
}

/** One pass of a multi-pass analytic (see backend `EnrichmentStageProgress`). */
export interface EnrichmentStageProgress {
  name: string;
  label: string;
  total: number;
  completed: number;
  /** Filtered out by this pass. */
  skipped: number;
  failed: number;
}

/** A distinct failure message and how many failed rows share it. */
export interface EnrichmentFailureReason {
  errorMessage: string | null;
  count: number;
}

/** One failed enrichment row, joined to the file it ran against. */
export interface FailedEnrichment {
  id: string;
  enrichableId: string;
  filename: string;
  path: string;
  uri: string;
  filetype: string;
  filetypeGroup: string;
  mimeType: string;
  size: number;
  errorMessage: string | null;
  retryCount: number;
  dateUpdated: string;
}

/** Failed enrichments for one dataset + analytic (see backend `DatasetEnrichmentFailures`). */
export interface DatasetEnrichmentFailures {
  datasetId: string;
  enrichmentType: string;
  total: number;
  returned: number;
  reasons: EnrichmentFailureReason[];
  items: FailedEnrichment[];
}
