import { PaginatedResponse, SortOrderType } from "@/types/common";

const ImageSortField = {
  Similarity: "similarity",
  DateTaken: "dateTaken",
} as const;

export type ImageSortFieldType =
  (typeof ImageSortField)[keyof typeof ImageSortField];

export interface BaseImageSearchParameters {
  dateFrom?: string;
  dateTo?: string;
  datasets?: string[];
  filetypes?: string[];
  tags?: string[];
  sortBy?: ImageSortFieldType;
  sortOrder?: SortOrderType;
  limit: number;
  page: number;
}
export interface ImageSimilaritySearchParameters extends BaseImageSearchParameters {
  minSimilarity?: number;
}

export interface TextImageKnnSearchRequest extends ImageSimilaritySearchParameters {
  query: string;
}

export interface ImagePublic {
  id: string;
  file_id: string;
  width: number;
  height: number;
  cameraMake?: string;
  cameraModel?: string;
  focalLength?: number;
  aperture?: number;
  iso?: number;
  dateTaken?: string;
  gpsAltitude?: number;
  tags: string[];
  embeddingModel?: string | null;
}

export type PaginatedImagesResponse = PaginatedResponse<ImagePublic>;

export interface ImageSimilarityResult extends ImagePublic {
  similarityScore: number;
}

export type PaginatedImageSimilarityResponse = PaginatedResponse<ImageSimilarityResult>;
