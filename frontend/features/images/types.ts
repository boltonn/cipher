import { PaginatedResponse, SortOrderType } from "@/types/common";

const ImageSortField = {
  Similarity: "similarity",
  DateTaken: "dateTaken",
  TagScore: "tagScore",
} as const;

export type ImageSortFieldType =
  (typeof ImageSortField)[keyof typeof ImageSortField];

/** `positive` -> `tags`, `negative` -> `negativeTags`; omitted clears the label. */
export type ModelTagType = "positive" | "negative";

export interface ImageTagRequest {
  imageIds: string[];
  tag: string;
  type?: ModelTagType;
}

/** One tag's labels for many images, saved in one call. */
export interface ImageAnnotateRequest {
  tag: string;
  positive: string[];
  negative: string[];
  /** Images to unlabel. */
  cleared: string[];
}

export interface ImageTagResult {
  updated: number;
}

export interface BaseImageSearchParameters {
  dateFrom?: string;
  dateTo?: string;
  datasets?: string[];
  filetypes?: string[];
  /** Labelled with any of these. */
  tags?: string[];
  /** Labelled as not any of these. */
  negativeTags?: string[];
  /** Unlabelled, and a model scored at least `minTagScore` on any of these. */
  predictedTags?: string[];
  minTagScore?: number;
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
  /** Set only on single-occurrence responses (e.g. GET /files/{id}/image); absent on search rows. */
  fileId?: string;
  width: number;
  height: number;
  cameraMake?: string;
  cameraModel?: string;
  focalLength?: number;
  aperture?: number;
  iso?: number;
  dateTaken?: string;
  gpsAltitude?: number;
  /** Positive labels: the image is this. */
  tags: string[];
  /** Negative labels: the image is explicitly not this. */
  negativeTags: string[];
  /** Model confidence (0-1) per tag -- a prediction, not a label. */
  tagScores: Record<string, number>;
  embeddingModel?: string | null;
}

export type PaginatedImagesResponse = PaginatedResponse<ImagePublic>;

export interface ImageSimilarityResult extends ImagePublic {
  similarityScore: number;
}

export type PaginatedImageSimilarityResponse = PaginatedResponse<ImageSimilarityResult>;
