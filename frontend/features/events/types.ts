/** Mirrors `cipher.schemas.graph.event` (camelCase over the wire). */

export const EVENT_TYPES = [
  "travel",
  "lodging",
  "reservation",
  "meeting",
  "deadline",
  "delivery",
  "occasion",
  "other",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export const EVENT_STATUSES = [
  "confirmed",
  "tentative",
  "cancelled",
  "completed",
] as const;
export type EventStatus = (typeof EVENT_STATUSES)[number];

export type DatePrecision = "exact" | "day" | "month" | "year" | "approximate";

export type EventSensitivity = "public" | "private" | "confidential";

/** iCalendar `PARTSTAT` — an invitee's response; null for non-invite events. */
export type RsvpStatus =
  | "needs-action"
  | "accepted"
  | "declined"
  | "tentative"
  | "delegated";

export type EventSortField = "date_start" | "date_created" | "date_updated";
export type SortOrder = "asc" | "desc";

export type ParticipantRole =
  | "traveler"
  | "attendee"
  | "organizer"
  | "host"
  | "guest";

export type PlaceRole = "venue" | "origin" | "destination";

export interface EventParticipant {
  id: string;
  eventId: string;
  entityId: string | null;
  rawName: string | null;
  /** iCalendar `mailto:` address — the precise key for resolution. */
  rawEmail: string | null;
  role: ParticipantRole;
  rsvpStatus: RsvpStatus | null;
  /** A room or resource, not a person. */
  isResource: boolean;
  dateCreated: string;
}

export interface EventPlace {
  id: string;
  eventId: string;
  locationId: string | null;
  rawText: string | null;
  role: PlaceRole;
  dateCreated: string;
}

/** Discriminated on `kind`; only some event types carry one. */
export interface EventDetails {
  kind: EventType;
  [field: string]: unknown;
}

export interface CipherEvent {
  id: string;
  /** Optional scoping ingest; null for analyst-authored / cross-dataset events. */
  datasetId: string | null;
  fileId: string | null;
  eventType: EventType;
  title: string;
  summary: string | null;
  dateStart: string;
  dateEnd: string | null;
  timezone: string | null;
  isAllDay: boolean;
  datePrecision: DatePrecision;
  status: EventStatus;
  details: EventDetails | null;
  /** Booking / meeting link (iCalendar `URL`). */
  url: string | null;
  /** Raw source labels (iCalendar `CATEGORIES`); distinct from analyst `tags`. */
  categories: string[];
  sensitivity: EventSensitivity | null;
  /** Stable source identifier (iCalendar `UID`). */
  uid: string | null;
  /** Raw iCalendar `RRULE`; not expanded into instances. */
  recurrenceRule: string | null;
  /** Source revision number (iCalendar `SEQUENCE`). */
  sequence: number | null;
  sourceCreated: string | null;
  sourceLastModified: string | null;
  extractor: string | null;
  extractionModel: string | null;
  confidence: number | null;
  isVerified: boolean;
  tags: string[];
  notes: string | null;
  /** Derived server-side from `eventType`; drives calendar colour. */
  category: string;
  dateCreated: string;
  dateUpdated: string;
}

export interface EventWithLinks extends CipherEvent {
  participants: EventParticipant[];
  places: EventPlace[];
}

export interface EventFilters {
  eventType?: EventType;
  category?: string;
  status?: EventStatus;
  isVerified?: boolean;
  dateFrom?: string;
  dateTo?: string;
}

export const EMPTY_EVENT_FILTERS: EventFilters = {};

export interface EventSearchParams extends EventFilters {
  datasetId?: string;
  query?: string;
  participantEntityId?: string;
  locationId?: string;
  sortBy?: EventSortField;
  sortOrder?: SortOrder;
  page?: number;
  limit?: number;
}

export interface PaginatedEvents {
  data: CipherEvent[];
  total: number;
  page: number;
  limit: number;
  hasMore: boolean;
}

export interface EventUpdatePayload {
  eventType?: EventType;
  title?: string;
  summary?: string | null;
  dateStart?: string;
  dateEnd?: string | null;
  timezone?: string | null;
  isAllDay?: boolean;
  datePrecision?: DatePrecision;
  status?: EventStatus;
  details?: EventDetails | null;
  url?: string | null;
  categories?: string[];
  sensitivity?: EventSensitivity | null;
  isVerified?: boolean;
  tags?: string[];
  notes?: string | null;
}

/** Body for `POST /events/{id}/participants` (camelCase over the wire). */
export interface EventParticipantCreatePayload {
  entityId?: string | null;
  rawName?: string | null;
  rawEmail?: string | null;
  role: ParticipantRole;
  rsvpStatus?: RsvpStatus | null;
  isResource?: boolean;
}

/** Body for `POST /events/{id}/places`. */
export interface EventPlaceCreatePayload {
  locationId?: string | null;
  rawText?: string | null;
  role: PlaceRole;
}
