import type { EntitySearchResult } from "@/features/entities/types";
import type { CipherEvent } from "@/features/events/types";
import type { FacePublic } from "@/features/faces/types";
import type { FileRecord } from "@/features/files/types";
import type { ImageSimilarityResult } from "@/features/images/types";
import type { FileSearchResultRaw } from "@/features/search/types";

/** Filter chips on the search page; they AND together across every lane. Dates are inclusive days. */
export interface OverviewFilters {
  entityIds: string[];
  /** Each group is one person/thing picked as several entities (spellings, addresses): any of it must be mentioned. */
  entityGroups?: string[][];
  filetypeGroups: string[];
  dateFrom?: string | null;
  dateTo?: string | null;
  /** Text results must contain the query as an exact phrase. */
  exactMatch?: boolean;
}

/** The stored, re-runnable part of a search (`SearchRequest`). */
export interface OverviewRequest {
  query: string;
  /** Empty = every dataset the user can access. */
  datasetIds: string[];
  filters: OverviewFilters;
  parentId?: string | null;
}

export type LaneName = "text" | "entities" | "images" | "files" | "events" | "places" | "faces";
export type LaneStatus = "ok" | "empty" | "timeout" | "error";
export type QueryKind = "selector" | "name" | "image" | "question" | "topic";

export interface MonthCount {
  /** `YYYY-MM` */
  month: string;
  files: number;
}

/** How a lane's hits spread over time and file type, over its top candidates. */
export interface ResultShape {
  dateHistogram: MonthCount[];
  filetypeGroups: Record<string, number>;
  sampleSize: number;
}

export interface Lane<T> {
  status: LaneStatus;
  items: T[];
  total: number;
  /** False when `total` is a floor ("500+"). */
  totalIsExact: boolean;
  shape: ResultShape | null;
  tookMs: number;
}

/** A location row, as much as the overview shows. */
export interface PlaceHit {
  id: string;
  name: string | null;
  category: string | null;
  city: string | null;
  adminArea: string | null;
  country: string | null;
  latitude: number;
  longitude: number;
}

export interface OverviewLayout {
  queryKind: QueryKind;
  hero: LaneName | null;
  /** Non-empty lanes, strongest first. */
  laneOrder: LaneName[];
  isQuestion: boolean;
  imageQuery: string | null;
}

export interface OverviewResponse {
  searchId: string;
  request: OverviewRequest;
  /** The searches this one was narrowed from, oldest first, ending with itself. */
  trail: SearchRecord[];
  layout: OverviewLayout;
  text: Lane<FileSearchResultRaw>;
  entities: Lane<EntitySearchResult>;
  images: Lane<ImageSimilarityResult>;
  files: Lane<FileRecord>;
  events: Lane<CipherEvent>;
  places: Lane<PlaceHit>;
  /** Faces of the people the query names, best detections first. */
  faces: Lane<FacePublic>;
  tookMs: number;
}

export interface SearchRecord extends OverviewRequest {
  id: string;
  userId: string;
  runCount: number;
  name: string | null;
  dateCreated: string;
  dateLastRun: string;
  dateSaved: string | null;
}

export interface AssistCitation {
  /** The `[n]` marker the answer uses for it. */
  number: number;
  fileId: string;
  chunkId: string;
  title: string;
}

/** AI part of a results page (backend default LLM), loaded after the results. */
export interface SearchAssist {
  /** Only for questions, grounded in the search's own top passages. */
  answer: string | null;
  citations: AssistCitation[];
  /** A narrower search read out of the wording -- offered, never applied automatically. */
  suggestion: { label: string; request: OverviewRequest } | null;
  /** The model reads the search as about what's in photos. */
  isVisual: boolean;
  /** Names in the search that could mean more than one entity; the user ticks which to search for. */
  nameChoices: NameChoice[];
  model: string;
}

/** One thing a typed name might mean: a person, an auto-created spelling, or an email address. */
export interface NameOption {
  entityIds: string[];
  displayName: string;
  entityType: EntitySearchResult["entityType"];
  isProvisional: boolean;
  detail: string | null;
  /** Ticked by default: very likely the same person. */
  isSuggested: boolean;
}

export interface NameChoice {
  /** As typed. */
  name: string;
  options: NameOption[];
}

export interface DatasetBrief {
  summary: string;
  suggestedSearches: string[];
  model: string;
  dateGenerated: string | null;
  /** The dataset profile was recomputed after this summary was written. */
  isOutdated: boolean;
}
