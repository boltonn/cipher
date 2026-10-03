import type {
  EntitySummary,
  EntityType,
  RelationshipType,
} from "@/features/entities/types";
import type { PaginatedResponse, SortOrderType } from "@/types/common";

/** One unit of a hierarchy, pointing at its `part_of` parent (cipher.schemas.graph.organization). */
export interface OrganizationTreeNode {
  entity: EntitySummary;
  parentId: string | null;
  /** Pending `part_of` suggestion that would attach this unit; null once confirmed. */
  suggestionId: string | null;
  category: string | null;
  /** People employed by / members of this unit directly. */
  memberCount: number;
  /** People tied to this unit by any other edge. */
  connectedCount: number;
}

/** GET /entities/{id}/structure/tree -- the whole hierarchy from its top-most ancestor. */
export interface OrganizationTree {
  rootId: string;
  nodes: OrganizationTreeNode[];
}

export type OrganizationAffiliation = "member" | "connected";

export type RelationshipSource =
  | "manual"
  | "extraction"
  | "selector_inference"
  | "co_mention"
  | "face_cooccurrence"
  | "import";

export type OrganizationPeopleSortKey =
  | "display_name"
  | "role"
  | "unit"
  | "relationship_type"
  | "source"
  | "mention_count"
  | "file_count"
  | "date_observed_end";

export interface OrganizationPeopleParameters {
  includeSubUnits: boolean;
  affiliation?: OrganizationAffiliation;
  relationshipTypes?: RelationshipType[];
  sources?: RelationshipSource[];
  query?: string;
  role?: string;
  unit?: string;
  isVerified?: boolean;
  page: number;
  limit: number;
  sortBy: OrganizationPeopleSortKey;
  sortOrder: SortOrderType;
}

/** One person<->unit edge (a person appears once per unit/edge they hold). */
export interface OrganizationPerson {
  relationshipId: string;
  person: EntitySummary;
  unit: EntitySummary;
  relationshipType: RelationshipType;
  affiliation: OrganizationAffiliation;
  role: string | null;
  source: RelationshipSource;
  mentionCount: number;
  fileCount: number;
  dateObservedStart: string | null;
  dateObservedEnd: string | null;
}

export type PaginatedOrganizationPeople = PaginatedResponse<OrganizationPerson>;

export type SuggestionMethod =
  | "co_mention"
  | "llm"
  | "selector_inference"
  | "manual"
  | "signature"
  | "email_domain";

/** The numbers behind an email-domain suggestion (cipher.orchestration.domain_affiliations). */
export interface EmailDomainExplanation {
  domain: string;
  addresses: string[];
  emailsSent: number;
  organization: string;
  organizationSignatures: number;
  domainSignatures: number;
  colleagues: string[];
  otherOrganizations: { name: string; signatures: number }[];
}

/**
 * A pending suggestion on a unit: a person `employed_by` / `member_of` it,
 * or a sub-unit `part_of` it.
 */
export interface OrganizationSuggestion {
  candidateId: string;
  entity: EntitySummary;
  unit: EntitySummary;
  relationshipType: RelationshipType;
  method: SuggestionMethod;
  role: string | null;
  confidence: number;
  explanation: EmailDomainExplanation | null;
}

/** One endpoint mention of a relation, offsets into the source text. */
export interface EvidenceSpan {
  mentionId: string;
  surfaceText: string;
  startOffset: number | null;
  endOffset: number | null;
}

/** GET /entities/relationship-candidates/{id}/evidence -- a source passage behind a suggestion. */
export interface RelationshipEvidence {
  /** null for a whole-email source (e.g. an email-domain suggestion's sent mail). */
  mentionRelationshipId: string | null;
  datasetId: string;
  fileId: string | null;
  extractor: string | null;
  confidence: number;
  attributes: Record<string, string>;
  src: EvidenceSpan | null;
  dst: EvidenceSpan | null;
  snippet: string;
  /** Offset of `snippet` in the source text; span offsets are absolute. */
  snippetOffset: number;
  subject: string | null;
  sender: string | null;
  dateSent: string | null;
}

/** One end of a name-level suggestion: a name as extracted, and what it might be. */
export interface NameSuggestionSide {
  name: string;
  normalizedValue: string;
  entityType: EntityType;
  /** Already resolved to this entity. */
  entity: EntitySummary | null;
  entityIsProvisional: boolean;
  /** The resolver's best guess, from the Resolve queue. */
  guess: EntitySummary | null;
  guessScore: number | null;
  /** Owns the sending address the signature was confirmed against -- preselected. */
  owner: EntitySummary | null;
  ownerAddress: string | null;
  unresolvedMentions: number;
}

/** A signature relationship whose names are not both settled yet (one per name pair). */
export interface NameSuggestion {
  datasetId: string;
  /** What produced it: an email signature, or a membership email (welcome / renewal). */
  extractor: "signature" | "membership";
  relationshipType: RelationshipType;
  source: NameSuggestionSide;
  target: NameSuggestionSide;
  role: string | null;
  sightings: number;
  mentionRelationshipIds: string[];
}

/** The reviewer's answer for one side: an existing entity id, or null to create `displayName`. */
export interface NameSuggestionChoice {
  normalizedValue: string;
  entityType: EntityType;
  entityId: string | null;
  displayName: string;
}
