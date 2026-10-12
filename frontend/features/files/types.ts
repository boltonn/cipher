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
  /** Positive tags on the file's content (shared by every copy of the same bytes). */
  tags: string[];
  negativeTags: string[];
  tagScores: Record<string, number>;
  /** Parent file this was extracted from (an email attachment's email, an archive member's archive). */
  parentId?: string | null;
  /** Set when the file was found compressed (report.csv.gz, logs.tar.gz). */
  compression?: CompressionInfo | null;
  /** Reading it needs a password: a password-protected file, or an archive holding encrypted members. */
  isEncrypted?: boolean;
}

export type Compression = "gzip" | "bzip2" | "xz" | "zstd" | "lz4";

/** How a file was compressed when found; the file's own hashes describe the decoded content. */
export interface CompressionInfo {
  encoding: Compression;
  /** Hashes and size of the file as found (compressed). */
  md5: string;
  sha256: string;
  size: number;
  /** Original name / modified time stored in the header (gzip). */
  filename: string | null;
  dateModified: string | null;
}

/** A file's AI summary: its summary chunk, shared by content-identical files. */
export interface FileSummary {
  chunkId: string;
  sha256: string;
  text: string;
  generatedBy: string | null;
  dateCreated: string;
}

/** Reconstructed extracted text for a file, from its indexed search chunks. */
export interface FileText {
  extractedTextId: string;
  text: string;
  chunkCount: number;
  /** Pages with no usable text layer (scanned) -- candidates for a stronger OCR re-run. */
  imagePages: number[];
  /** Pages whose text came from OCR. */
  ocrPages: number[];
  /** OCR engine/model that produced `ocrPages`, e.g. "easyocr". */
  ocrModel: string | null;
  /** An analyst corrected this text; pipeline re-runs no longer overwrite it. */
  isContentCorrected: boolean;
  contentCorrectedBy: string | null;
  /** `[start, end)` stretches (code points) a person wrote; zero-width where text was only deleted. */
  correctedRanges: [number, number][];
}

/** A file's corrected text, applied to every copy of the same content. */
export interface TextCorrectionRequest {
  content: string;
  /** Steps that already read the old text to redo on the new one (from a dry run's `rerunnable`). */
  rerun?: string[];
  /** Only report what the correction would do. */
  dryRun?: boolean;
}

/** A mention the correction renames or can't place. */
export interface CorrectedMention {
  mentionId: string;
  /** Entity or selector type. */
  label: string;
  surfaceText: string;
  newSurfaceText: string | null;
}

/** What a correction did, or would do on a dry run, across every copy of the file's content. */
export interface TextCorrectionSummary {
  /** Files whose text changes (copies of the same content). */
  fileCount: number;
  /** Mentions on unchanged text, moved to their new offsets. */
  keptCount: number;
  renamed: CorrectedMention[];
  /** Mentions whose text is gone; deleted on save. */
  lost: CorrectedMention[];
  correctedRanges: [number, number][];
  /** Search chunks moved onto (or rebuilt from) the corrected text. */
  chunkCount: number;
  /** Steps that already read the old text and can be redone on the new one. */
  rerunnable: string[];
  /** Steps redone or put back to pending. */
  rerun: string[];
  /** Steps running on these files right now; saving is refused. */
  running: string[];
  isSaved: boolean;
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
  /** Files found inside it (archive members, email attachments); listed at its `path`, like a folder's files. */
  memberCount?: number;
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
  parentId?: string | null;
  compression?: CompressionInfo | null;
  isEncrypted?: boolean;
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
