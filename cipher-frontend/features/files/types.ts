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

export type FileBrowserEntryType = "file" | "directory";

/** One row in a dataset's file browser -- a file or a folder. Folders have no id/hashes/size. */
export interface FileBrowserItem {
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
