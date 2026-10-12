export type IconComponent = React.ComponentType<{ className?: string }>;

export type PaginationModeType = "infinite" | "normal";

export type SortOrderType = "asc" | "desc";

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
  hasMore: boolean;
}
