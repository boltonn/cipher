"use client";
import { personsService } from "@/features/persons/api";
import type { PersonCreate, PersonSearchParameters, PersonUpdate } from "@/features/persons/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export function usePersonSearch(params: PersonSearchParameters) {
  return useQuery({
    queryKey: ["persons", "search", params],
    queryFn: () => personsService.search(params),
  });
}

/** Resolve a person's display name by id; React Query dedupes repeated ids across many cards. */
export function usePerson(personId: string | undefined) {
  return useQuery({
    queryKey: ["persons", personId],
    queryFn: () => personsService.getById(personId as string),
    enabled: !!personId,
    staleTime: 60_000,
  });
}

export function useCreatePerson(onSuccess?: (personId: string) => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: PersonCreate) => personsService.create(payload),
    onSuccess: (person) => {
      queryClient.invalidateQueries({ queryKey: ["persons"] });
      onSuccess?.(person.id);
    },
  });
}

export function useCreatePersonFromImage(onSuccess?: (personId: string) => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ file, payload }: { file: File; payload: PersonCreate & { faceIndex?: number } }) =>
      personsService.createFromImage(file, payload),
    onSuccess: (person) => {
      queryClient.invalidateQueries({ queryKey: ["persons"] });
      // the backend runs the similarity sweep inline, so by now other faces
      // may have flipped to `matched` with a fresh pending candidate
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      queryClient.invalidateQueries({ queryKey: ["face-matches"] });
      onSuccess?.(person.id);
    },
  });
}

/**
 * Create a person directly from an already-detected face -- no re-upload or
 * re-detection needed. Goes through the same backend endpoint as the other
 * creation paths, so it also runs the same inline match-proposal sweep
 * (composing separate assign/set-representative calls client-side, like the
 * old version of this hook did, would silently skip that).
 */
export function useCreatePersonFromFace(onSuccess?: (personId: string) => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ faceId, payload }: { faceId: string; payload: PersonCreate }) =>
      personsService.createFromFace(faceId, payload),
    onSuccess: (person) => {
      queryClient.invalidateQueries({ queryKey: ["persons"] });
      // the backend runs the similarity sweep inline, so by now other faces
      // may have flipped to `matched` with a fresh pending candidate
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      queryClient.invalidateQueries({ queryKey: ["face-matches"] });
      onSuccess?.(person.id);
    },
  });
}

export function useUpdatePerson(personId: string, onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: PersonUpdate) => personsService.update(personId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["persons"] });
      onSuccess?.();
    },
  });
}

/**
 * Fold `sourceId` into `targetId` and delete the source record. The
 * backend moves faces, pending matches, event participations, comments,
 * mentions and relationship edges onto the survivor, so invalidate broadly.
 */
export function useMergePerson(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ targetId, sourceId }: { targetId: string; sourceId: string }) =>
      personsService.merge(targetId, sourceId),
    onSuccess: (_result, { sourceId }) => {
      // The merged-in person (and its shared-id entity) is deleted -- drop its
      // cache outright so a still-mounted observer doesn't refetch a 404, and
      // exclude its keys from the broad invalidation below.
      queryClient.removeQueries({ queryKey: ["persons", sourceId] });
      queryClient.removeQueries({ queryKey: ["entities", sourceId] });
      const notSource = (key: readonly unknown[]) => key[1] !== sourceId;
      queryClient.invalidateQueries({ queryKey: ["persons"], predicate: (q) => notSource(q.queryKey) });
      queryClient.invalidateQueries({ queryKey: ["entities"], predicate: (q) => notSource(q.queryKey) });
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      queryClient.invalidateQueries({ queryKey: ["face-matches"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["comments"] });
      onSuccess?.();
    },
  });
}

/**
 * Delete a person and their bridged entity node. Faces are unlinked rather
 * than deleted; mentions/relationships/comments on the bridge entity go too
 * -- invalidate the same breadth as a merge, since the effect is similar
 * (this person's records disappear from every list that showed them).
 */
export function useDeletePerson(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (personId: string) => personsService.delete(personId),
    onSuccess: (_result, personId) => {
      // The page viewing this person is still mounted until the route change
      // lands. Removing a query that has a live observer makes the observer
      // rebuild it on its next render and refetch a 404 -- so only drop the
      // unobserved ones and leave the rest to gc once the page unmounts.
      queryClient.removeQueries({ queryKey: ["persons", personId], type: "inactive" });
      queryClient.removeQueries({ queryKey: ["entities", personId], type: "inactive" });
      const notDeleted = (key: readonly unknown[]) => key[1] !== personId;
      queryClient.invalidateQueries({ queryKey: ["persons"], predicate: (q) => notDeleted(q.queryKey) });
      queryClient.invalidateQueries({ queryKey: ["entities"], predicate: (q) => notDeleted(q.queryKey) });
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      queryClient.invalidateQueries({ queryKey: ["face-matches"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["comments"] });
      onSuccess?.();
    },
  });
}

/** Ranked shortlist of other persons who may be the same identity as `personId`. */
export function usePersonMergeCandidates(personId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["persons", personId, "merge-candidates"],
    queryFn: () => personsService.mergeCandidates(personId as string),
    enabled: !!personId && enabled,
    staleTime: 30_000,
  });
}

export function usePersonRepresentativeFaces(personId: string | undefined) {
  return useQuery({
    queryKey: ["persons", personId, "representative-faces"],
    queryFn: () => personsService.getRepresentativeFaces(personId as string),
    enabled: !!personId,
  });
}

export function useAddPersonExample(personId: string, onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ file, faceIndex }: { file: File; faceIndex: number }) =>
      personsService.addExample(personId, file, faceIndex),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["persons", personId, "representative-faces"] });
      // the inline similarity sweep can flip any unassigned face to `matched`,
      // not just this person's -- refresh the whole faces browser and the
      // pending-match lists, like the other person-creation paths do
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      queryClient.invalidateQueries({ queryKey: ["face-matches"] });
      onSuccess?.();
    },
  });
}
