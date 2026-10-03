import { useQuery } from "@tanstack/react-query";
import { tagService } from "../api";
import type { TagTargetType } from "../types";

/** The most used tag names for a kind of target -- suggestions for tag pickers and filters. */
export function useTagNames(targetType: TagTargetType) {
  return useQuery({
    queryKey: ["tags", "names", targetType],
    queryFn: () => tagService.names(targetType),
    staleTime: 60_000,
  });
}
