import { organizationsService } from "@/features/organizations/api";
import type {
  NameSuggestion,
  NameSuggestionChoice,
  OrganizationPeopleParameters,
} from "@/features/organizations/types";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

/** The whole hierarchy an organization unit sits in. */
export function useOrganizationTree(entityId: string) {
  return useQuery({
    queryKey: ["entities", entityId, "structure", "tree"],
    queryFn: () => organizationsService.getTree(entityId),
  });
}

/** People within / connected to a unit, one row per edge; keeps the last page while the next loads. */
export function useOrganizationPeople(
  unitId: string | undefined,
  params: OrganizationPeopleParameters
) {
  return useQuery({
    queryKey: ["entities", unitId, "structure", "people", params],
    queryFn: () => organizationsService.listPeople(unitId as string, params),
    enabled: !!unitId,
    placeholderData: keepPreviousData,
  });
}

/** Pending people suggested for a unit or anything below it. */
export function useOrganizationSuggestions(unitId: string) {
  return useQuery({
    queryKey: ["entities", unitId, "structure", "suggestions"],
    queryFn: () => organizationsService.getSuggestions(unitId),
  });
}

/** Accept or reject a suggestion, then refresh every structure view (tree counts, table, suggestions). */
export function useResolveSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      candidateId,
      status,
    }: {
      candidateId: string;
      status: "confirmed" | "rejected";
    }) => organizationsService.resolveSuggestion(candidateId, status),
    onSuccess: () =>
      qc.invalidateQueries({
        predicate: (q) =>
          q.queryKey[0] === "entities" && q.queryKey[2] === "structure",
      }),
    onError: (error) =>
      toast.error(
        error instanceof Error ? error.message : "Couldn't save that decision"
      ),
  });
}

/** The source passages behind a suggestion, fetched when its dialog opens. */
export function useSuggestionEvidence(candidateId: string | undefined) {
  return useQuery({
    queryKey: ["relationship-candidates", candidateId, "evidence"],
    queryFn: () => organizationsService.getEvidence(candidateId as string),
    enabled: !!candidateId,
  });
}

/** Signature relationships on a unit (or below) whose names are not settled yet. */
export function useNameSuggestions(unitId: string) {
  return useQuery({
    queryKey: ["entities", unitId, "structure", "name-suggestions"],
    queryFn: () => organizationsService.getNameSuggestions(unitId),
  });
}

/** Signature employers that are not an organization yet (no entity, no resolver guess). */
export function useUnplacedNameSuggestions() {
  return useQuery({
    queryKey: ["name-suggestions", "unplaced"],
    queryFn: organizationsService.getUnplacedNameSuggestions,
  });
}

export function useNameSuggestionEvidence(ids: string[] | undefined) {
  return useQuery({
    queryKey: ["name-suggestions", "evidence", ids],
    queryFn: () =>
      organizationsService.getNameSuggestionEvidence(ids as string[]),
    enabled: !!ids?.length,
  });
}

/** Accept / dismiss a name-level suggestion, then refresh structure views, entity lists and the Resolve queue. */
export function useReviewNameSuggestion() {
  const qc = useQueryClient();
  const refresh = () =>
    qc.invalidateQueries({
      predicate: (q) =>
        q.queryKey[0] === "name-suggestions" ||
        (q.queryKey[0] === "entities" &&
          (q.queryKey[2] === "structure" || q.queryKey[1] === "list")),
    });
  const onError = (error: unknown) =>
    toast.error(
      error instanceof Error ? error.message : "Couldn't save that decision"
    );
  return {
    accept: useMutation({
      mutationFn: (args: {
        suggestion: NameSuggestion;
        source: NameSuggestionChoice;
        target: NameSuggestionChoice;
      }) =>
        organizationsService.acceptNameSuggestion(
          args.suggestion,
          args.source,
          args.target
        ),
      onSuccess: refresh,
      onError,
    }),
    dismiss: useMutation({
      mutationFn: (suggestion: NameSuggestion) =>
        organizationsService.dismissNameSuggestion(
          suggestion.mentionRelationshipIds
        ),
      onSuccess: refresh,
      onError,
    }),
  };
}
