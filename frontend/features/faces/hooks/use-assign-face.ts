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
      facesService.assignMany(faceIds, {
        personId,
        assignmentMethod: "manual",
      }),
    onSuccess: (updated, { personName }) => {
      for (const queryKey of [
        ["faces"],
        ["face-matches"],
        ["persons"],
        ["graph-explore"],
      ])
        queryClient.invalidateQueries({ queryKey });
      toast.success(
        `Assigned ${updated.toLocaleString()} face${updated === 1 ? "" : "s"} to ${personName || "person"}`
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
      facesService.assignMany(faceIds, { personId: null }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      queryClient.invalidateQueries({ queryKey: ["persons"] });
      toast.success(
        `Unassigned ${updated.toLocaleString()} face${updated === 1 ? "" : "s"}`
      );
      onSuccess?.();
    },
    onError: () => toast.error("Couldn't unassign faces"),
  });
}
