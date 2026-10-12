import type {
  CipherEvent,
  EventParticipant,
  EventParticipantCreatePayload,
  EventPlace,
  EventLinkPick,
  EventMonthCount,
  EventParticipantOption,
  EventPlaceCreatePayload,
  EventPlaceOption,
  EventSearchParams,
  EventUpdatePayload,
  EventWithLinks,
  PaginatedEvents,
} from "@/features/events/types";
import { apiClient } from "@/lib/api-client";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

const eventsBaseURL = "/events";

const ids = (picks: EventLinkPick[] = [], extra: string[] = []) => {
  const all = [...extra, ...picks.flatMap((p) => (p.id ? [p.id] : []))];
  return all.length ? all : undefined;
};
const names = (picks: EventLinkPick[] = []) => {
  const all = picks.flatMap((p) => (p.id ? [] : [p.name]));
  return all.length ? all : undefined;
};

function toQuery(params: EventSearchParams) {
  return {
    datasetIds: params.datasetIds,
    participantEntityIds: ids(params.participants, params.participantEntityIds),
    participantNames: names(params.participants),
    locationIds: ids(params.places, params.locationIds),
    placeNames: names(params.places),
    query: params.query || undefined,
    eventType: params.eventType,
    category: params.category || undefined,
    status: params.status,
    isVerified: params.isVerified,
    dateFrom: params.dateFrom,
    dateTo: params.dateTo,
    sortBy: params.sortBy,
    sortOrder: params.sortOrder,
    page: params.page,
    limit: params.limit,
  };
}

export const eventsService = {
  list: (params: EventSearchParams): Promise<PaginatedEvents> =>
    apiClient
      .get<PaginatedEvents>(eventsBaseURL, { params: toQuery(params) })
      .then((res) => res.data),

  calendar: (params: EventSearchParams): Promise<CipherEvent[]> =>
    apiClient
      .get<CipherEvent[]>(`${eventsBaseURL}/calendar`, { params: toQuery(params) })
      .then((res) => res.data),

  participants: (args: { datasetIds?: string[]; q?: string }): Promise<EventParticipantOption[]> =>
    apiClient
      .get<EventParticipantOption[]>(`${eventsBaseURL}/participants`, {
        params: { datasetIds: args.datasetIds, q: args.q || undefined },
      })
      .then((res) => res.data),

  places: (args: { datasetIds?: string[]; q?: string }): Promise<EventPlaceOption[]> =>
    apiClient
      .get<EventPlaceOption[]>(`${eventsBaseURL}/places`, {
        params: { datasetIds: args.datasetIds, q: args.q || undefined },
      })
      .then((res) => res.data),

  getById: (id: string): Promise<EventWithLinks> =>
    apiClient.get<EventWithLinks>(`${eventsBaseURL}/${id}`).then((res) => res.data),

  update: (id: string, payload: EventUpdatePayload): Promise<CipherEvent> =>
    apiClient
      .patch<CipherEvent>(`${eventsBaseURL}/${id}`, payload)
      .then((res) => res.data),

  remove: (id: string): Promise<void> =>
    apiClient.delete(`${eventsBaseURL}/${id}`).then(() => undefined),

  markInvalid: (eventIds: string[]): Promise<void> =>
    apiClient
      .post(`${eventsBaseURL}/mark-invalid`, { eventIds })
      .then(() => undefined),

  addParticipant: (
    eventId: string,
    body: EventParticipantCreatePayload
  ): Promise<EventParticipant> =>
    apiClient
      .post<EventParticipant>(`${eventsBaseURL}/${eventId}/participants`, body)
      .then((res) => res.data),

  removeParticipant: (participantId: string): Promise<void> =>
    apiClient
      .delete(`${eventsBaseURL}/participants/${participantId}`)
      .then(() => undefined),

  addPlace: (eventId: string, body: EventPlaceCreatePayload): Promise<EventPlace> =>
    apiClient
      .post<EventPlace>(`${eventsBaseURL}/${eventId}/places`, body)
      .then((res) => res.data),

  removePlace: (placeId: string): Promise<void> =>
    apiClient.delete(`${eventsBaseURL}/places/${placeId}`).then(() => undefined),

  months: (datasetIds?: string[]): Promise<EventMonthCount[]> =>
    apiClient
      .get<EventMonthCount[]>(`${eventsBaseURL}/months`, { params: { datasetIds } })
      .then((res) => res.data),

  categories: (args: {
    datasetIds?: string[];
    q?: string;
    limit?: number;
  }): Promise<string[]> =>
    apiClient
      .get<string[]>(`${eventsBaseURL}/categories`, {
        params: {
          datasetIds: args.datasetIds,
          q: args.q || undefined,
          limit: args.limit ?? 50,
        },
      })
      .then((res) => res.data),

  tags: (args: { datasetIds?: string[]; q?: string; limit?: number }): Promise<string[]> =>
    apiClient
      .get<string[]>(`${eventsBaseURL}/tags`, {
        params: {
          datasetIds: args.datasetIds,
          q: args.q || undefined,
          limit: args.limit ?? 50,
        },
      })
      .then((res) => res.data),
};

export function useEvents(params: EventSearchParams, enabled = true) {
  return useQuery({
    queryKey: ["events", "list", params],
    queryFn: () => eventsService.list(params),
    enabled,
    placeholderData: keepPreviousData,
  });
}

/** Matching events whose `dateStart` falls in the `dateFrom`..`dateTo` window — the calendar feed. */
export function useEventsCalendar(params: EventSearchParams & { dateFrom: string; dateTo: string }) {
  return useQuery({
    queryKey: ["events", "calendar", params],
    queryFn: () => eventsService.calendar(params),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

/** Event counts per month — the calendar's month/year jump picker. */
export function useEventMonths(datasetIds?: string[]) {
  return useQuery({
    queryKey: ["events", "months", datasetIds],
    queryFn: () => eventsService.months(datasetIds),
    staleTime: 60_000,
  });
}

/** Who is on events (linked entities + unresolved names), most events first. */
export function useEventParticipantOptions(args: { datasetIds?: string[]; q?: string }, enabled = true) {
  return useQuery({
    queryKey: ["events", "participants", args],
    queryFn: () => eventsService.participants(args),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

/** Where events happen (linked locations + unresolved place text), most events first. */
export function useEventPlaceOptions(args: { datasetIds?: string[]; q?: string }, enabled = true) {
  return useQuery({
    queryKey: ["events", "places", args],
    queryFn: () => eventsService.places(args),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

/** Distinct source-label (iCalendar CATEGORIES) values for the filter combobox. */
export function useEventCategoryOptions(args: { datasetIds?: string[]; q?: string }) {
  return useQuery({
    queryKey: ["events", "categories", args],
    queryFn: () => eventsService.categories(args),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

/** Distinct analyst `tags` in use, most-used first -- powers the tag input's suggestions. */
export function useEventTagOptions(args: { datasetIds?: string[]; q?: string }, enabled = true) {
  return useQuery({
    queryKey: ["events", "tags", args],
    queryFn: () => eventsService.tags(args),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

export function useEvent(eventId: string | undefined) {
  return useQuery({
    queryKey: ["events", eventId],
    queryFn: () => eventsService.getById(eventId as string),
    enabled: !!eventId,
    staleTime: 15_000,
  });
}

export function useUpdateEvent(eventId: string, onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EventUpdatePayload) =>
      eventsService.update(eventId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["events"] });
      onSuccess?.();
    },
  });
}

/** Invalidate the list, calendar, and this event's detail so every view refreshes. */
function useEventLinkMutation<TArgs>(
  eventId: string,
  fn: (args: TArgs) => Promise<unknown>
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["events", eventId] });
    },
    onError: (e) => toast.error((e as Error).message || "Change failed"),
  });
}

export function useAddParticipant(eventId: string) {
  return useEventLinkMutation(eventId, (body: EventParticipantCreatePayload) =>
    eventsService.addParticipant(eventId, body)
  );
}

export function useRemoveParticipant(eventId: string) {
  return useEventLinkMutation(eventId, (participantId: string) =>
    eventsService.removeParticipant(participantId)
  );
}

export function useAddPlace(eventId: string) {
  return useEventLinkMutation(eventId, (body: EventPlaceCreatePayload) =>
    eventsService.addPlace(eventId, body)
  );
}

export function useRemovePlace(eventId: string) {
  return useEventLinkMutation(eventId, (placeId: string) =>
    eventsService.removePlace(placeId)
  );
}

export function useDeleteEvent(onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventId: string) => eventsService.remove(eventId),
    onSuccess: (_, eventId) => {
      // Drop the open detail query first so the invalidation doesn't refetch a deleted event.
      qc.removeQueries({ queryKey: ["events", eventId] });
      qc.invalidateQueries({ queryKey: ["events"] });
      toast.success("Event marked invalid");
      onSuccess?.();
    },
  });
}

export function useMarkEventsInvalid(onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventIds: string[]) => eventsService.markInvalid(eventIds),
    onSuccess: (_, eventIds) => {
      for (const eventId of eventIds) {
        qc.removeQueries({ queryKey: ["events", eventId] });
      }
      qc.invalidateQueries({ queryKey: ["events"] });
      toast.success(
        `${eventIds.length.toLocaleString()} ${eventIds.length === 1 ? "event" : "events"} marked invalid`
      );
      onSuccess?.();
    },
    onError: (e) => toast.error((e as Error).message || "Change failed"),
  });
}
