/** How a table's rows are attributed to a dataset. */
export type TableScope = "dataset" | "file" | "shared";

export interface TableMetrics {
  name: string;
  scope: TableScope;
  /** Table + indexes + TOAST. */
  totalBytes: number;
  indexBytes: number;
  /** Planner estimate; null until the table is analyzed. */
  rowCount: number | null;
}

/** A dataset's rows in one table; bytes are its row share of the table's size. */
export interface DatasetTableUsage {
  tableName: string;
  rowCount: number;
  estimatedBytes: number;
  estimatedIndexBytes: number;
}

export interface DatasetDatabaseUsage {
  datasetId: string;
  datasetName: string;
  rowCount: number;
  estimatedBytes: number;
  estimatedIndexBytes: number;
  tables: DatasetTableUsage[];
}

export interface DatabaseMetrics {
  databaseSizeBytes: number;
  tables: TableMetrics[];
  datasets: DatasetDatabaseUsage[];
}
