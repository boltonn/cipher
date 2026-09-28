import { PaginatedResponse, SortOrderType } from "@/types/common";

export type PersonSourceType = "manual" | "face_clustering";
export type SexType = "female" | "male";

const PersonSortField = {
  Name: "name",
  DateCreated: "dateCreated",
  DateUpdated: "dateUpdated",
} as const;

export type PersonSortFieldType = (typeof PersonSortField)[keyof typeof PersonSortField];

export interface Person {
  id: string;
  name?: string;
  aliases: string[];
  notes?: string;
  tags: string[];
  dateOfBirth?: string;
  sex?: SexType;
  isVerified: boolean;
  source: PersonSourceType;
  dateCreated: string;
  dateUpdated: string;
}

export interface PersonCreate {
  name?: string;
  aliases?: string[];
  notes?: string;
  tags?: string[];
  dateOfBirth?: string;
  sex?: SexType;
  isVerified?: boolean;
}

export interface PersonUpdate {
  name?: string;
  aliases?: string[];
  notes?: string;
  tags?: string[];
  dateOfBirth?: string;
  sex?: SexType;
  isVerified?: boolean;
}

export interface PersonMergeResult {
  personId: string;
  facesMoved: number;
  matchesMoved: number;
  eventParticipantsMoved: number;
  commentsMoved: number;
  mentionsMoved: number;
  relationshipsMoved: number;
  relationshipCandidatesMoved: number;
  entityMatchesMoved: number;
}

/** A person whose representative faces resemble another person's -- a merge lead. */
export interface PersonMergeSuggestion extends Person {
  similarityScore: number;
}

export interface PersonSearchParameters {
  query?: string;
  tags?: string[];
  isVerified?: boolean;
  sortBy?: PersonSortFieldType;
  sortOrder?: SortOrderType;
  limit: number;
  page: number;
}

export type PaginatedPersonsResponse = PaginatedResponse<Person>;
