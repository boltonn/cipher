export type IconComponent = React.ComponentType<{ className?: string }>;

const PaginationMode = {
  Infinite: "infinite",
  Normal: "normal",
} as const;

export type PaginationModeType =
  (typeof PaginationMode)[keyof typeof PaginationMode];

const SortOrder = {
  Ascending: "asc",
  Descending: "desc",
} as const;

export type SortOrderType = (typeof SortOrder)[keyof typeof SortOrder];

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
  hasMore: boolean;
}
