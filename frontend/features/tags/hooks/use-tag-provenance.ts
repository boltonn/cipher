import { useMe } from "@/features/users/hooks/use-me";
import { useQuery } from "@tanstack/react-query";
import { tagService } from "../api";
import type { Tag, TagTarget } from "../types";

const UNKNOWN_SOURCE = "unknown";

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

function describe(row: Tag): string {
  if (row.sourceName === UNKNOWN_SOURCE)
    return "Added before tag history was recorded";
  const who =
    row.sourceType === "model"
      ? `model ${row.sourceDisplayName}`
      : row.sourceDisplayName;
  return `Added by ${who} · ${formatDate(row.dateUpdated)}`;
}

/**
 * Who or what set each positive tag on a target, for `TagsInput`'s `describeTag` /
 * `confirmRemove`: model tags are flagged, and removing a tag another user added asks first
 * (removal clears it for everyone). Refreshed after any mutation (see the query provider).
 */
export function useTagProvenance(target: TagTarget | undefined) {
  const { data: me } = useMe();
  const { data: rows = [] } = useQuery({
    queryKey: ["tags", target?.targetType, target?.targetId],
    queryFn: () => tagService.list(target as TagTarget),
    enabled: !!target?.targetId,
    staleTime: 0,
  });

  // Newest first from the API, so the first positive label per tag is the one in effect.
  const labelsByTag = new Map<string, Tag[]>();
  for (const row of rows) {
    if (row.label !== "positive") continue;
    labelsByTag.set(row.tag, [...(labelsByTag.get(row.tag) ?? []), row]);
  }

  const describeTag = (tag: string) => {
    const latest = labelsByTag.get(tag)?.[0];
    return latest
      ? { label: describe(latest), isModel: latest.sourceType === "model" }
      : undefined;
  };

  const confirmRemove = (tag: string) => {
    const others = (labelsByTag.get(tag) ?? []).filter(
      (row) => row.sourceType === "user" && row.sourceName !== me?.id
    );
    if (others.length === 0) return undefined;
    const names = [...new Set(others.map((row) => row.sourceDisplayName))];
    const who =
      names[0] === UNKNOWN_SOURCE
        ? "someone before tag history was recorded"
        : names.join(", ");
    return `Added by ${who}. Removing it takes it off for everyone.`;
  };

  return { describeTag, confirmRemove };
}
