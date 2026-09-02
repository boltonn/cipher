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
