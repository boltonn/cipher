import { PaginatedResponse, SortOrderType } from "@/types/common";

export type FaceSortFieldType = "dateCreated" | "qualityScore" | "detectionConfidence";

export type FaceAssignmentMethodType = "manual" | "automatic";

/** Datastore-wide "same face" floor (mirrors the backend's `DEFAULT_FACE_SIMILARITY`):
 * matching, clustering and "not a face" auto-rejection all use it, and the filter panel defaults to it. */
export const DEFAULT_MIN_SIMILARITY = 0.61;

export interface BaseFaceSearchParameters {
  imageId?: string;
  personId?: string;
  unassignedOnly?: boolean;
  representativeOnly?: boolean;
  /** Only faces marked "not a face" (otherwise they're excluded everywhere). */
  rejectedOnly?: boolean;
  minQuality?: number;
  /** Minimum face crop size in pixels (shorter of width/height). */
  minSize?: number;
  /** Faces assigned to, or with a pending match for, any of these persons. */
  personIds?: string[];
  /** Only faces in images from these datasets (the backend limits this to the user's access). */
  datasets?: string[];
  sortBy?: FaceSortFieldType;
  sortOrder?: SortOrderType;
  limit: number;
  page: number;
}

export type FaceStatusType = "unmatched" | "matched" | "verified" | "rejected";

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
  /** Set when marked "not a face" (detector false positive, e.g. a pet). */
  dateRejected?: string;
  /** manual = an analyst said so; automatic = resembles a face an analyst rejected. */
  rejectionMethod?: FaceAssignmentMethodType;
  /** Similarity to the analyst-rejected face that triggered an automatic rejection. */
  rejectionConfidence?: number;
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

export interface FaceRejection {
  faceIds: string[];
  /** Also auto-reject unassigned faces this similar (e.g. more photos of the same cat). */
  rejectSimilar?: boolean;
  minSimilarity?: number;
}

export interface FaceRejectionResult {
  updated: number;
  autoRejected: number;
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
export type PaginatedFaceSimilarityResponse =
  PaginatedResponse<FaceSimilarityResult>;

export type FaceMatchStatusType = "pending" | "confirmed" | "rejected";
export type FaceMatchMethodType =
  | "automaticSimilarity"
  | "automaticClustering"
  | "manual";

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
