import type {
  CipherEvent,
  EventParticipant,
  EventParticipantCreatePayload,
  EventPlace,
  EventPlaceCreatePayload,
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

function toQuery(params: EventSearchParams) {
  return {
    datasetId: params.datasetId,
    query: params.query || undefined,
    eventType: params.eventType,
    category: params.category || undefined,
    status: params.status,
    participantEntityId: params.participantEntityId,
    locationId: params.locationId,
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

  calendar: (args: {
    dateFrom: string;
    dateTo: string;
    datasetId?: string;
  }): Promise<CipherEvent[]> =>
    apiClient
      .get<CipherEvent[]>(`${eventsBaseURL}/calendar`, {
        params: {
          dateFrom: args.dateFrom,
          dateTo: args.dateTo,
          datasetId: args.datasetId,
        },
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

  categories: (args: {
    datasetId?: string;
    q?: string;
    limit?: number;
  }): Promise<string[]> =>
    apiClient
      .get<string[]>(`${eventsBaseURL}/categories`, {
        params: {
          datasetId: args.datasetId,
          q: args.q || undefined,
          limit: args.limit ?? 50,
        },
      })
      .then((res) => res.data),

  tags: (args: { datasetId?: string; q?: string; limit?: number }): Promise<string[]> =>
    apiClient
      .get<string[]>(`${eventsBaseURL}/tags`, {
        params: {
          datasetId: args.datasetId,
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

/** Events whose `dateStart` falls in a window — the calendar feed. */
export function useEventsCalendar(args: {
  dateFrom: string;
  dateTo: string;
  datasetId?: string;
  enabled?: boolean;
}) {
  const { enabled = true, ...rest } = args;
  return useQuery({
    queryKey: ["events", "calendar", rest],
    queryFn: () => eventsService.calendar(rest),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

/** Distinct source-label (iCalendar CATEGORIES) values for the filter combobox. */
export function useEventCategoryOptions(args: { datasetId?: string; q?: string }) {
  return useQuery({
    queryKey: ["events", "categories", args],
    queryFn: () => eventsService.categories(args),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

/** Distinct analyst `tags` in use, most-used first -- powers the tag input's suggestions. */
export function useEventTagOptions(args: { datasetId?: string; q?: string }, enabled = true) {
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["events"] });
      toast.success("Event deleted");
      onSuccess?.();
    },
  });
}
