import type { SortOrderType } from "@/types/common";

/** A single loaded file. Named FileRecord (not File) to avoid shadowing the DOM File type. */
export interface FileRecord {
  id: string;
  datasetId: string;
  filename: string;
  filetypeGroup: string;
  filetype: string;
  filetypeName?: string;
  md5: string;
  sha256: string;
  mimeType: string;
  path?: string;
  uri?: string;
  /** Storage device/bucket/mount the file lives on, e.g. "s3://my-bucket". */
  device?: string;
  size: number;
  dateCreated?: string;
  dateLastUpdated?: string;
}

/** Reconstructed extracted text for a file, from its indexed search chunks. */
export interface FileText {
  text: string;
  chunkCount: number;
}

/** One extracted table's cells, split into a header row and (possibly capped) data rows. */
export interface FileTableSheet {
  columns: string[];
  rows: string[][];
  totalRows: number;
  truncated: boolean;
}

/** A file's structured tables, if extraction found any (csv/tsv/json/jsonl/xlsx/...). */
export interface FileTables {
  sheets: FileTableSheet[];
}

export type FileBrowserEntryType = "file" | "directory";

/** One row in a dataset's file browser -- a file or a folder. Folders have no id/hashes/size. */
export interface FileBrowserItem {
  /** File ID; unset for directories. */
  id?: string;
  type: FileBrowserEntryType;
  filename: string;
  filetypeGroup: string;
  filetype: string;
  filetypeName?: string;
  md5: string;
  sha256: string;
  mimeType: string;
  path?: string;
  uri?: string;
  device?: string;
  size: number;
  dateCreated?: string;
  dateLastUpdated?: string;
}

export interface FileBrowserRequest {
  query?: string;
  /** Folder path to list; omit to list the whole dataset flat. */
  path?: string;
  filetype?: string;
  filetypeGroup?: string;
  limit?: number;
  page?: number;
  sortBy?: "filename" | "dateCreated" | "dateLastUpdated";
  sortOrder?: SortOrderType;
}

export interface FileBrowserResponse {
  data: FileBrowserItem[];
  total: number;
  page: number;
  limit: number;
  hasMore: boolean;
}

/** Normalized [0,1] region on a page, e.g. from a document chunk's bounding box. */
export interface BoundingBox {
  top: number;
  left: number;
  width: number;
  height: number;
}

/** Where in a file's viewer to jump to -- e.g. from a search result or a chat citation.
 * `pageNumber` drives PDF/PPTX (slide)/DOCX; `startOffset`/`endOffset` drive the
 * character-range highlight used for email (and as a fallback elsewhere). */
export interface FileLocationTarget {
  pageNumber?: number;
  boundingBox?: BoundingBox;
  startOffset?: number;
  endOffset?: number;
}
