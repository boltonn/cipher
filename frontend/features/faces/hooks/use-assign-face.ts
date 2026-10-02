"use client";
import { facesService } from "@/features/faces/api";
import type { FaceAssignment } from "@/features/faces/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

export function useAssignFace(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      assignment,
    }: {
      id: string;
      assignment: FaceAssignment;
    }) => facesService.assign(id, assignment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      onSuccess?.();
    },
  });
}

/** Assign several faces to one person (a manual decision, like the triage panel's picker). */
export function useAssignFaces(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      faceIds,
      personId,
    }: {
      faceIds: string[];
      personId: string;
      personName?: string;
    }) =>
      Promise.all(
        faceIds.map((id) =>
          facesService.assign(id, { personId, assignmentMethod: "manual" })
        )
      ),
    onSuccess: (faces, { personName }) => {
      for (const queryKey of [
        ["faces"],
        ["face-matches"],
        ["persons"],
        ["graph-explore"],
      ])
        queryClient.invalidateQueries({ queryKey });
      toast.success(
        `Assigned ${faces.length.toLocaleString()} face${faces.length === 1 ? "" : "s"} to ${personName || "person"}`
      );
      onSuccess?.();
    },
    onError: () => {
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      toast.error("Couldn't assign faces");
    },
  });
}

/** Detach several faces from their person ("wrong person", not "not a face"). */
export function useUnassignFaces(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (faceIds: string[]) =>
      Promise.all(
        faceIds.map((id) => facesService.assign(id, { personId: null }))
      ),
    onSuccess: (faces) => {
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      queryClient.invalidateQueries({ queryKey: ["persons"] });
      toast.success(
        `Unassigned ${faces.length.toLocaleString()} face${faces.length === 1 ? "" : "s"}`
      );
      onSuccess?.();
    },
    onError: () => toast.error("Couldn't unassign faces"),
  });
}
