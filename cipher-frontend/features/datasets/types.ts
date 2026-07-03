import { SortOrderType } from "@/types/common";
import { z } from "zod";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const DatasetSortField = {
  Name: "name",
  DateCreated: "dateCreated",
  DateLastUpdated: "dateLastUpdated",
} as const;

export type DatasetSortFieldType =
  (typeof DatasetSortField)[keyof typeof DatasetSortField];

export interface Dataset {
  id: string;
  name: string;
  description: string;
  dateCreated: string;
  dateLastUpdated: string;
}

export const DatasetCreateSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
});

export type DatasetCreate = z.infer<typeof DatasetCreateSchema>;

export interface DatasetRequest {
  query?: string;
  dateCreated?: string;
  dateLastUpdated?: string;
  sortBy?: DatasetSortFieldType;
  sortOrder?: SortOrderType;
  limit?: number;
}
