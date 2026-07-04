export type DataTableColumnType = "text" | "date" | "number" | "enum";

export interface DataTableEnumOption {
  label: string;
  value: string;
}

/**
 * Describes one column of a DataTable: how to read/render it, and whether
 * (and how) it can be sorted or filtered. This is the "give it a TypeScript
 * object" schema the table is driven by -- it knows nothing about any
 * specific entity type.
 */
export interface DataTableColumn<T> {
  /** Stable key. Also the backend filter/sort param name for this column. */
  key: string;
  header: string;
  type: DataTableColumnType;
  sortable?: boolean;
  filterable?: boolean;
  align?: "left" | "right";
  /** Custom cell renderer; defaults to String(row[key]). */
  render?: (row: T) => React.ReactNode;
  /** Options for type: "enum" columns, shown as filter checkboxes. */
  enumOptions?: DataTableEnumOption[];
  /** Fixed column width (e.g. "120px" or "1fr"); omit to size automatically. */
  width?: string;
}

export type DataTableSortOrder = "asc" | "desc";

export interface DataTableSortState {
  sortBy?: string;
  sortOrder?: DataTableSortOrder;
}

/**
 * Generic per-column filter values, keyed by column.key:
 * - text: string
 * - date: { from?: string; to?: string }
 * - number: { min?: number; max?: number }
 * - enum: string[]
 */
export type DataTableFilterValue =
  | string
  | string[]
  | { from?: string; to?: string }
  | { min?: number; max?: number }
  | undefined;

export type DataTableFilters = Record<string, DataTableFilterValue>;
