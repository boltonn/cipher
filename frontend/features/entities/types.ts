import { PaginatedResponse, SortOrderType } from "@/types/common";

export const ENTITY_TYPES = [
  "person",
  "organization",
  "location",
  "selector",
] as const;
export type EntityType = (typeof ENTITY_TYPES)[number];

/** A graph node's kind: every entity type, plus `event` (reached through a `participant_in` edge). */
export const GRAPH_NODE_TYPES = [...ENTITY_TYPES, "event"] as const;
export type GraphNodeType = (typeof GRAPH_NODE_TYPES)[number];

export const SELECTOR_TYPES = [
  "phone",
  "email",
  "ip",
  "iban",
  "bank_card",
  "passport",
  "national_id",
  "imei",
  "imsi",
  "social_handle",
  "crypto_address",
  "license_plate",
  "domain",
] as const;
export type SelectorType = (typeof SELECTOR_TYPES)[number];

export const SELECTOR_TYPE_LABELS: Record<SelectorType, string> = {
  phone: "Phone",
  email: "Email",
  ip: "IP address",
  iban: "IBAN",
  bank_card: "Bank card",
  passport: "Passport",
  national_id: "National ID",
  imei: "IMEI",
  imsi: "IMSI",
  social_handle: "Social handle",
  crypto_address: "Crypto address",
  license_plate: "License plate",
  domain: "Website",
};

/** Specific provider / network / scheme within a selector type. Optional. */
export const SELECTOR_SUBTYPES = [
  "telegram",
  "instagram",
  "facebook",
  "whatsapp",
  "signal",
  "twitter",
  "tiktok",
  "vk",
  "odnoklassniki",
  "wechat",
  "qq",
  "weibo",
  "douyin",
  "soroush",
  "bale",
  "rubika",
  "eitaa",
  "btc_address",
  "eth_address",
  "xmr_address",
  "tron_address",
  "ru_inn",
  "ru_snils",
  "cn_ric",
  "ir_code_melli",
] as const;
export type SelectorSubtype = (typeof SELECTOR_SUBTYPES)[number];

/** Which broad SelectorType a subtype rolls up to (mirrors backend SELECTOR_SUBTYPES). */
export const SELECTOR_SUBTYPE_TYPE: Record<SelectorSubtype, SelectorType> = {
  telegram: "social_handle",
  instagram: "social_handle",
  facebook: "social_handle",
  whatsapp: "social_handle",
  signal: "social_handle",
  twitter: "social_handle",
  tiktok: "social_handle",
  vk: "social_handle",
  odnoklassniki: "social_handle",
  wechat: "social_handle",
  qq: "social_handle",
  weibo: "social_handle",
  douyin: "social_handle",
  soroush: "social_handle",
  bale: "social_handle",
  rubika: "social_handle",
  eitaa: "social_handle",
  btc_address: "crypto_address",
  eth_address: "crypto_address",
  xmr_address: "crypto_address",
  tron_address: "crypto_address",
  ru_inn: "national_id",
  ru_snils: "national_id",
  cn_ric: "national_id",
  ir_code_melli: "national_id",
};

export const RELATIONSHIP_TYPES = [
  "has_selector",
  "member_of",
  "employed_by",
  "part_of",
  "subsidiary_of",
  "located_in",
  "emailed",
  "family_of",
  "appears_in_photo_with",
  "co_mention_of",
  "same_as",
  "owns",
  "participant_in",
] as const;
export type RelationshipType = (typeof RELATIONSHIP_TYPES)[number];

/** Edges the graph derives at read time (from `event_participant`) -- never in the stored relationship list. */
export const DERIVED_RELATIONSHIPS: RelationshipType[] = ["participant_in"];

/** Edge types dropped from graph views as low-signal (none today; face co-occurrence stays visible). */
export const LOW_SIGNAL_RELATIONSHIPS: RelationshipType[] = [];

/**
 * Inverse of a gender-neutral `family_of` role, seen from the target's side.
 * Mirrors the backend `FAMILY_ROLE_INVERSE` (cipher.schemas.ontology).
 */
export const FAMILY_ROLE_INVERSE: Record<string, string> = {
  parent: "child",
  child: "parent",
  grandparent: "grandchild",
  grandchild: "grandparent",
  aunt_uncle: "niece_nephew",
  niece_nephew: "aunt_uncle",
  sibling: "sibling",
  spouse: "spouse",
  cousin: "cousin",
  relative: "relative",
};

/** One relationship type from `GET /entities/ontology` -- the single source of truth. */
export interface OntologyRelationship {
  relationshipType: RelationshipType;
  label: string;
  directed: boolean;
  symmetric: boolean;
  allowedSrc: EntityType[];
  allowedDst: EntityType[];
  inverseLabel: string | null;
  description: string;
  roles: string[];
}

export interface Ontology {
  entityTypes: EntityType[];
  selectorTypes: SelectorType[];
  selectorSubtypes: Partial<Record<SelectorType, SelectorSubtype[]>>;
  relationships: OntologyRelationship[];
}

export type TraversalDirection = "out" | "in" | "both";
export type MentionedType = "extracted_text" | "image" | "structured_field";

/** How a mention was found -- its evidence class. Mirrors backend MentionProvenance. */
export const MENTION_PROVENANCES = [
  "text",
  "email_header",
  "metadata",
  "image",
  "pattern",
] as const;
export type MentionProvenance = (typeof MENTION_PROVENANCES)[number];
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
  /** Curated alternate names -- not every name resolved to the entity (see ResolvedName). */
  aliases: string[];
  tags: string[];
  notes?: string;
  source: EntitySource;
  isVerified: boolean;
  personId?: string;
  locationId?: string | null;
  /** Minted by the resolver, not yet merged into a canonical entity or promoted. */
  isProvisional: boolean;
  /** only set when entityType === "selector" */
  selectorType?: SelectorType | null;
  selectorSubtype?: SelectorSubtype | null;
  dateCreated: string;
  dateUpdated: string;
}

/** An entity row in the dataset table: the evidence behind it and its open review work. */
export interface EntityListItem extends Entity {
  mentionCount: number;
  fileCount: number;
  relationshipCount: number;
  /** pending Resolve-queue candidates + merge candidates naming this entity */
  pendingMatchCount: number;
}

export interface EntityBreakdownItem {
  key: string;
  count: number;
}

/** Entity / selector counts for a dataset -- feeds the dataset-view chart. */
export interface EntityBreakdown {
  total: number;
  byEntityType: EntityBreakdownItem[];
  bySelectorType: EntityBreakdownItem[];
  bySelectorSubtype: EntityBreakdownItem[];
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
  attributes: Record<string, unknown>;
  entity: EntitySummary;
  /** edge weight -- for emailed, the emails sent that way */
  weight?: number | null;
  /** for selector neighbours: mentions carrying the selector's normalized value */
  mentionCount?: number | null;
  selectorType?: SelectorType | null;
  selectorSubtype?: SelectorSubtype | null;
  normalizedValue?: string | null;
}

export type RelatedEntitySort = "weight" | "recent" | "name";

/** Type-specific detail row (organization / location / selector / person), camelCase. */
export interface EntityDetail {
  legalName?: string;
  /** Organization: free-text kind (company, agency, division, office…), like a location's category. */
  category?: string;
  /** Organization: the entity id of the organization this one is part of. */
  parentId?: string | null;
  country?: string;
  addressText?: string;
  latitude?: number;
  longitude?: number;
  adminArea?: string;
  selectorType?: SelectorType;
  selectorSubtype?: SelectorSubtype | null;
  rawValue?: string;
  normalizedValue?: string;
  regionHint?: string;
  // person detail (read-only here)
  name?: string;
  dateOfBirth?: string;
  sex?: string;
  nationality?: string;
  [key: string]: unknown;
}

export interface Mention {
  id: string;
  datasetId: string;
  entityId?: string | null;
  mentionedType: MentionedType;
  /** derived evidence class, sent by the API */
  provenance: MentionProvenance;
  mentionedId: string;
  fileId?: string | null;
  surfaceText: string;
  entityType?: EntityType | null;
  selectorType?: SelectorType | null;
  selectorSubtype?: SelectorSubtype | null;
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
  datasetId: string | null;
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

/** A traversal node: an entity, or an event. Mirrors backend `GraphNode`. */
export interface GraphNode extends Omit<EntitySummary, "entityType"> {
  entityType: GraphNodeType;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: EntityRelationship[];
}

/** A linked selector plus how many mentions carry its normalized value (any dataset, resolved or not). */
export interface SelectorMention {
  entityId: string;
  selectorType: SelectorType | null;
  selectorSubtype?: SelectorSubtype | null;
  normalizedValue: string | null;
  mentionCount: number;
  /** Distinct files where this address is a From/Sender header (email selectors). */
  sentCount?: number;
  /** Distinct files where this address is a To/Cc/Bcc header (email selectors). */
  receivedCount?: number;
  /** Body-text mentions of the value produced by NER. */
  textCount?: number;
  /** Body-text mentions of the value found by deterministic pattern match. */
  patternCount?: number;
}

/** One phone-parsing region the selector normalizer accepts (ISO-3166-1 alpha-2). */
export interface SelectorRegion {
  code: string;
  callingCode: number;
}

export interface EntityProfile {
  entity: Entity;
  detail?: EntityDetail | null;
  selectors: EntitySummary[];
  selectorMentions: SelectorMention[];
  /** mention count keyed by MentionProvenance (text / email_header / metadata / image / pattern) */
  mentionCounts: Partial<Record<MentionProvenance, number>>;
  /** distinct files this entity is mentioned in -- the headline number */
  fileCount: number;
  /** highest-weight neighbours only; full list via GET /entities/{id}/related */
  relatedEntities: RelatedEntity[];
  relatedTotal: number;
  selectorTotal: number;
  topMentions: Mention[];
  faceIds: string[];
}

export type ResolutionBand = "auto" | "review" | "provisional";

export type FeatureLevel =
  | "conflict"
  | "none"
  | "weak"
  | "moderate"
  | "strong"
  | "exact";

export interface ResolutionFeature {
  name: string;
  level: FeatureLevel;
  weight: number;
  contribution: number;
  detail?: string | null;
}

export interface ResolutionExplanation {
  score: number;
  band: ResolutionBand;
  autoRule?: string | null;
  blocking: string[];
  candidatesConsidered: number;
  runnerUpScore?: number | null;
  features: ResolutionFeature[];
}

export type DecisionSource =
  | "analyst"
  | "sibling_auto"
  | "reconcile"
  | "system_auto";

export interface EntityMatch {
  id: string;
  datasetId: string;
  entityId: string;
  mentionId?: string | null;
  /** Name-group key; set (with mentionId null) on group-level rows. */
  normalizedValue?: string | null;
  mentionCount?: number | null;
  provisionalEntityId?: string | null;
  similarityScore: number;
  matchMethod: string;
  decisionSource?: DecisionSource | null;
  explanation?: ResolutionExplanation | null;
  /** Display name + type of `entityId`, populated by the grouped queue only. */
  entityName?: string | null;
  entityType?: EntityType | null;
  /** `personId` of `entityId` when it bridges a person record (grouped queue only). */
  entityPersonId?: string | null;
  /** Display name of `provisionalEntityId` on a merge proposal (merge queue only). */
  provisionalName?: string | null;
  /** `entityId` is a provisional entity, not a canonical one (grouped queue only). */
  entityIsProvisional?: boolean | null;
  /** Pending merge proposals filed against a provisional `entityId` (grouped queue only). */
  entityPendingMergeCount?: number | null;
  status: EntityMatchStatus;
  reviewedBy?: string | null;
  reviewedAt?: string | null;
  reviewNote?: string | null;
  dateCreated: string;
}

/** One card in the grouped resolution review queue. */
export interface EntityMatchGroup {
  datasetId: string;
  normalizedValue: string;
  surface: string;
  mentionCount: number;
  fileCount: number;
  status: EntityMatchStatus;
  top: EntityMatch;
  alternatives: EntityMatch[];
}

export type PaginatedEntityMatchGroupsResponse = PaginatedResponse<EntityMatchGroup> & {
  /** Name groups left out because their only candidates are provisional (auto-created) entities. */
  hiddenProvisionalTotal: number;
};

/** One card in the entity-merge review queue: a provisional stub + canonical targets. */
export interface EntityMergeGroup {
  datasetId: string;
  provisionalEntityId: string;
  provisionalName: string;
  provisionalEntityType: EntityType;
  mentionCount: number;
  status: EntityMatchStatus;
  candidates: EntityMatch[];
}

export type PaginatedEntityMergeGroupsResponse =
  PaginatedResponse<EntityMergeGroup>;

export interface EntityMatchBatchItem {
  matchId: string;
  status: EntityMatchStatus;
  reviewNote?: string;
}

export interface EntitySearchParameters {
  query?: string;
  datasetId?: string;
  entityType?: EntityType;
  selectorType?: SelectorType;
  selectorSubtype?: SelectorSubtype;
  tags?: string[];
  isVerified?: boolean;
  /** Auto-created by the resolver, not yet verified or merged (selectors excluded). */
  provisional?: boolean;
  country?: string;
  category?: string;
  dateOfBirthFrom?: string;
  dateOfBirthTo?: string;
  limit: number;
  page: number;
  sortBy?: EntitySortKey;
  sortOrder?: SortOrderType;
}

export type EntitySortKey =
  | "display_name"
  | "date_created"
  | "date_updated"
  | "mention_count"
  | "relevance";

export interface EntityCreatePayload {
  datasetId: string;
  entityType: EntityType;
  displayName: string;
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

/** A name the evidence uses for an entity (a resolved name group); aliases are the curated subset. */
export interface ResolvedName {
  normalizedValue: string;
  surface: string;
  mentionCount: number;
  isAlias: boolean;
}

/** An entity a selector is linked to by `has_selector`, and how (`manual`, `selector_inference`, ...). */
export interface SelectorOwner {
  entityId: string;
  displayName: string;
  source: string;
}

/** What the data says about who uses a selector (backend `SelectorEvidence`). */
export interface SelectorEvidence {
  entityId: string;
  displayName: string;
  /** Emails with this address in a header. */
  emailCount: number;
  /** Display names seen next to it in headers, most frequent first. */
  names: string[];
  linkedTo: SelectorOwner[];
}

export interface SelectorLinkPayload {
  selectorType: SelectorType;
  selectorSubtype?: SelectorSubtype | null;
  rawValue: string;
  regionHint?: string | null;
}

export interface MentionCreatePayload {
  datasetId: string;
  entityId?: string | null;
  mentionedType: MentionedType;
  mentionedId: string;
  fileId?: string | null;
  surfaceText: string;
  entityType?: EntityType | null;
  selectorType?: SelectorType | null;
  selectorSubtype?: SelectorSubtype | null;
  startOffset?: number | null;
  endOffset?: number | null;
  context?: string | null;
  extractor?: string;
}

export interface MentionUpdatePayload {
  entityId?: string | null;
  entityType?: EntityType | null;
  selectorType?: SelectorType | null;
  selectorSubtype?: SelectorSubtype | null;
  surfaceText?: string;
  /** Move the span (send both, plus the new `surfaceText`); the backend re-keys its name group. */
  startOffset?: number;
  endOffset?: number;
  context?: string;
}

/** `GET /mentions/{id}/resolution` -- the resolver's scored candidates for a mention's name group. */
export interface MentionResolution {
  mentionId: string;
  normalizedValue?: string | null;
  resolvedEntityId?: string | null;
  resolvedBy?: "system" | "analyst" | null;
  candidates: {
    id: string;
    entityId: string;
    status: EntityMatchStatus;
    similarityScore: number;
    matchMethod: string;
  }[];
}

export interface MentionResolvePayload {
  entityId?: string | null;
  newEntity?: EntityCreatePayload | null;
  newEntityDetail?: Record<string, unknown> | null;
}

/** One distinct unresolved name in the review queue (grouped, not per-mention). */
export interface UnresolvedNameGroup {
  normalizedValue: string;
  surface: string;
  mentionCount: number;
  fileCount: number;
  sampleContext?: string | null;
  suggestedType?: EntityType | null;
  /** Pending resolutions: entities the resolver proposes this name group is, best first. */
  resolutions: EntityMatch[];
}

export interface ResolveNameGroupPayload {
  datasetId: string;
  normalizedValue: string;
  entityType: EntityType;
  /** attach to an existing entity; omit to create a new one from the name */
  entityId?: string;
  displayName?: string;
}

export type PaginatedEntitiesResponse = PaginatedResponse<EntityListItem>;
export type PaginatedMentionsResponse = PaginatedResponse<Mention>;
export type PaginatedUnresolvedNamesResponse =
  PaginatedResponse<UnresolvedNameGroup>;
export type PaginatedRelationshipsResponse =
  PaginatedResponse<EntityRelationship>;
export type PaginatedRelatedEntitiesResponse = PaginatedResponse<RelatedEntity>;
export type PaginatedEntityMatchesResponse = PaginatedResponse<EntityMatch>;

/** A person tied to an organization by `employed_by` / `member_of`. */
export interface OrganizationMember {
  entity: EntitySummary;
  relationshipType: RelationshipType;
  role?: string | null;
}

/** GET /entities/{id}/structure -- an organization's hierarchy, locations and people (from edges). */
export interface OrganizationStructure {
  /** Parent first, then its parent, … */
  ancestors: EntitySummary[];
  children: EntitySummary[];
  locations: EntitySummary[];
  members: OrganizationMember[];
}
