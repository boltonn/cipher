import { PaginatedResponse, SortOrderType } from "@/types/common";

const FaceSortField = {
  DateCreated: "dateCreated",
  Quality: "qualityScore",
  DetectionConfidence: "detectionConfidence",
} as const;

export type FaceSortFieldType = (typeof FaceSortField)[keyof typeof FaceSortField];

export type FaceAssignmentMethodType = "manual" | "automatic";

/** Datastore-wide default for "this counts as a match" (mirrors the backend's
 * `DEFAULT_FACE_MATCH_SIMILARITY`): the floor used whenever similarity search
 * runs without an analyst-chosen threshold, and the filter panel's default. */
export const DEFAULT_MIN_SIMILARITY = 0.61;

export interface BaseFaceSearchParameters {
  imageId?: string;
  personId?: string;
  unassignedOnly?: boolean;
  representativeOnly?: boolean;
  minQuality?: number;
  /** Minimum face crop size in pixels (shorter of width/height). */
  minSize?: number;
  /** Faces assigned to, or with a pending match for, any of these persons. */
  personIds?: string[];
  sortBy?: FaceSortFieldType;
  sortOrder?: SortOrderType;
  limit: number;
  page: number;
}

export type FaceStatusType = "unmatched" | "matched" | "verified";

export interface FaceSimilaritySearchParameters extends BaseFaceSearchParameters {
  minSimilarity?: number;
}

export interface FaceBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FaceLandmark {
  x: number;
  y: number;
  label?: string;
}

export interface FacePose {
  yaw: number;
  pitch: number;
  roll: number;
}

export interface FacePublic {
  id: string;
  imageId: string;
  uri: string;
  boundingBox: FaceBoundingBox;
  landmarks: FaceLandmark[];
  detectorModel?: string;
  detectionConfidence?: number;
  qualityScore?: number;
  pose?: FacePose;
  embeddingModel?: string;
  personId?: string;
  /** Assigned person's name, denormalized so a face grid needn't fetch it per card. */
  personName?: string;
  assignmentMethod?: FaceAssignmentMethodType;
  isRepresentative: boolean;
  isPrimary: boolean;
  status: FaceStatusType;
  /** Top pending-match candidate's person, when not yet assigned. */
  candidatePersonId?: string;
  candidatePersonName?: string;
}

export interface FaceSimilarityResult extends FacePublic {
  similarityScore: number;
}

export interface FaceAssignment {
  personId: string | null;
  assignmentMethod?: FaceAssignmentMethodType;
  assignmentConfidence?: number;
}

export interface FaceRepresentativeUpdate {
  isRepresentative?: boolean;
  isPrimary?: boolean;
}

/** A face detected in an uploaded photo, not yet persisted. */
export interface DetectedFace {
  boundingBox: FaceBoundingBox;
  landmarks: FaceLandmark[];
  confidence: number;
  embedding: number[];
}

export type PaginatedFacesResponse = PaginatedResponse<FacePublic>;
export type PaginatedFaceSimilarityResponse = PaginatedResponse<FaceSimilarityResult>;

export type FaceMatchStatusType = "pending" | "confirmed" | "rejected";
export type FaceMatchMethodType = "automatic_similarity" | "automatic_clustering" | "manual";

/** A candidate face-to-person match awaiting (or having received) analyst review. */
export interface FaceMatch {
  id: string;
  faceId: string;
  personId: string;
  similarityScore: number;
  matchMethod: FaceMatchMethodType;
  status: FaceMatchStatusType;
  reviewedBy?: string;
  reviewedAt?: string;
  reviewNote?: string;
  dateCreated: string;
}

export interface FaceMatchSearchParameters {
  faceId?: string;
  personId?: string;
  status?: FaceMatchStatusType;
  minSimilarity?: number;
  limit: number;
  page: number;
}

export type PaginatedFaceMatchesResponse = PaginatedResponse<FaceMatch>;
