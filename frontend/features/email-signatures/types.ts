import type { Mention, RelationshipType } from "@/features/entities/types";
import type { PaginatedResponse } from "@/types/common";

/** A relationship between two mentions of one text (mirrors `MentionRelationshipView`). */
export interface MentionRelationship {
  id: string;
  datasetId: string;
  srcMentionId: string;
  dstMentionId: string;
  relationshipType: RelationshipType;
  confidence: number;
  fileId: string | null;
  attributes: Record<string, string>;
  /** `signature` (the email-signature reader), `manual` (drawn by an analyst), an NER model... */
  extractor: string | null;
  dateReviewed: string | null;
  /** true accepted, false rejected, null pending */
  isAccepted: boolean | null;
  dateCreated: string;
  src: Mention;
  dst: Mention;
}

export interface MentionRelationshipDraft {
  srcMentionId: string;
  dstMentionId: string;
  relationshipType: RelationshipType;
  attributes?: Record<string, string>;
}

export interface MentionRelationshipUpdate {
  relationshipType?: RelationshipType;
  attributes?: Record<string, string>;
  reverse?: boolean;
}

/** Where an email's email signature sits in its extracted text. */
export interface EmailSignature {
  fileId: string;
  datasetId: string;
  extractedTextId: string;
  startOffset: number;
  endOffset: number;
  subject: string | null;
  sender: string | null;
  dateSent: string | null;
}

export interface EmailSignatureSummary {
  fileId: string;
  datasetId: string;
  subject: string | null;
  sender: string | null;
  dateSent: string | null;
  personName: string | null;
  /** broadest first */
  organizations: string[];
  relationshipCount: number;
  pendingCount: number;
}

export interface EmailSignatureSearchParameters {
  datasetIds?: string[];
  /** true: emails with relationships left to review; false: fully reviewed; undefined: all */
  isPending?: boolean;
  query?: string;
  page: number;
  limit: number;
}

export type PaginatedEmailSignatures = PaginatedResponse<EmailSignatureSummary>;
