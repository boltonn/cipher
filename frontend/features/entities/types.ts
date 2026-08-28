import { PaginatedResponse, SortOrderType } from "@/types/common";

export const ENTITY_TYPES = [
  "person",
  "organization",
  "location",
  "selector",
] as const;
export type EntityType = (typeof ENTITY_TYPES)[number];

export const SELECTOR_KINDS = [
  "phone",
  "email",
  "passport",
  "national_id",
  "imei",
  "iban",
  "handle",
  "crypto_address",
  "license_plate",
] as const;
export type SelectorKind = (typeof SELECTOR_KINDS)[number];

export const RELATIONSHIP_TYPES = [
  "has_selector",
  "member_of",
  "employed_by",
  "part_of",
  "subsidiary_of",
  "located_in",
  "communicates_with",
  "family_of",
  "associate_of",
  "same_as",
  "owns",
] as const;
export type RelationshipType = (typeof RELATIONSHIP_TYPES)[number];

/** Co-mention edges hidden from graph traversal by default (matches the backend). */
export const LOW_SIGNAL_RELATIONSHIPS: RelationshipType[] = ["associate_of"];

export type TraversalDirection = "out" | "in" | "both";
export type MentionedType = "extracted_text" | "image" | "structured_field";
export type EntitySource =
  | "extraction"
  | "manual"
  | "import"
  | "face_clustering";
export type EntityMatchStatus = "pending" | "confirmed" | "rejected";

export interface Entity {
  id: string;
  /** null for dataset-agnostic nodes such as a person bridge entity */
  datasetId: string | null;
  entityType: EntityType;
  displayName: string;
  displayNameNormalized: string;
  aliases: string[];
  tags: string[];
  notes?: string;
  source: EntitySource;
  isVerified: boolean;
  personId?: string;
  dateCreated: string;
  dateUpdated: string;
}

export interface EntitySummary {
  id: string;
  entityType: EntityType;
  displayName: string;
  isVerified: boolean;
}

export interface EntitySearchResult extends EntitySummary {
  matchReason: string;
  score: number;
}

export interface RelatedEntity {
  relationshipType: RelationshipType;
  direction: "out" | "in";
  entity: EntitySummary;
}

/** Type-specific detail row. Comes back from the backend with snake_case keys
 * (the profile endpoint does not alias the nested dict), so both cases are read. */
export interface EntityDetail {
  legalName?: string;
  legal_name?: string;
  orgType?: string;
  org_type?: string;
  country?: string;
  addressText?: string;
  address_text?: string;
  latitude?: number;
  longitude?: number;
  adminArea?: string;
  admin_area?: string;
  selectorKind?: SelectorKind;
  selector_kind?: SelectorKind;
  rawValue?: string;
  raw_value?: string;
  normalizedValue?: string;
  normalized_value?: string;
  regionHint?: string;
  region_hint?: string;
  // person detail (read-only here)
  name?: string;
  dateOfBirth?: string;
  date_of_birth?: string;
  sex?: string;
  nationality?: string;
  [key: string]: unknown;
}

export interface Mention {
  id: string;
  datasetId: string;
  entityId?: string | null;
  mentionedType: MentionedType;
  mentionedId: string;
  fileId?: string | null;
  surfaceText: string;
  entityType?: EntityType | null;
  selectorKind?: SelectorKind | null;
  normalizedValue?: string | null;
  startOffset?: number | null;
  endOffset?: number | null;
  boundingBox?: Record<string, number> | null;
  fieldPath?: string | null;
  context?: string | null;
  extractor?: string | null;
  extractionModel?: string | null;
  extractionConfidence?: number | null;
  dateCreated: string;
  dateUpdated: string;
}

export interface EntityRelationship {
  id: string;
  datasetId: string;
  srcEntityId: string;
  dstEntityId: string;
  relationshipType: RelationshipType;
  directed: boolean;
  weight?: number | null;
  source: string;
  attributes: Record<string, unknown>;
  dateObservedStart?: string | null;
  dateObservedEnd?: string | null;
  dateCreated: string;
  dateUpdated: string;
}

export interface GraphResponse {
  nodes: EntitySummary[];
  edges: EntityRelationship[];
}

export interface EntityProfile {
  entity: Entity;
  detail?: EntityDetail | null;
  selectors: EntitySummary[];
  mentionCounts: Record<string, number>;
  relatedEntities: RelatedEntity[];
  topMentions: Mention[];
  faceIds: string[];
}

export interface EntityMatch {
  id: string;
  datasetId: string;
  entityId: string;
  mentionId?: string | null;
  provisionalEntityId?: string | null;
  similarityScore: number;
  matchMethod: string;
  status: EntityMatchStatus;
  reviewedBy?: string | null;
  reviewedAt?: string | null;
  reviewNote?: string | null;
  dateCreated: string;
}

export interface EntitySearchParameters {
  query?: string;
  datasetId?: string;
  entityType?: EntityType;
  selectorKind?: SelectorKind;
  tags?: string[];
  isVerified?: boolean;
  country?: string;
  orgType?: string;
  dateOfBirthFrom?: string;
  dateOfBirthTo?: string;
  limit: number;
  page: number;
  sortBy?: "display_name" | "date_created" | "date_updated";
  sortOrder?: SortOrderType;
}

export interface EntityCreatePayload {
  datasetId: string;
  entityType: EntityType;
  displayName: string;
  aliases?: string[];
  tags?: string[];
  notes?: string;
  source?: EntitySource;
  isVerified?: boolean;
}

export interface EntityUpdatePayload {
  displayName?: string;
  aliases?: string[];
  tags?: string[];
  notes?: string;
  isVerified?: boolean;
}

export interface MentionCreatePayload {
  datasetId: string;
  entityId?: string | null;
  mentionedType: MentionedType;
  mentionedId: string;
  fileId?: string | null;
  surfaceText: string;
  entityType?: EntityType | null;
  selectorKind?: SelectorKind | null;
  startOffset?: number | null;
  endOffset?: number | null;
  context?: string | null;
  extractor?: string;
}

export interface MentionUpdatePayload {
  entityId?: string | null;
  entityType?: EntityType | null;
  selectorKind?: SelectorKind | null;
  surfaceText?: string;
  context?: string;
}

export interface MentionResolvePayload {
  entityId?: string | null;
  newEntity?: EntityCreatePayload | null;
  newEntityDetail?: Record<string, unknown> | null;
  reviewedBy: string;
}

export type PaginatedEntitiesResponse = PaginatedResponse<Entity>;
export type PaginatedMentionsResponse = PaginatedResponse<Mention>;
export type PaginatedRelationshipsResponse =
  PaginatedResponse<EntityRelationship>;
export type PaginatedEntityMatchesResponse = PaginatedResponse<EntityMatch>;
