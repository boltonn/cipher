"use client";

import { Button } from "@/components/ui/button";
import { MentionsByFile } from "@/features/entities/components/mentions-by-file";
import { useEntityMentionsInfinite } from "@/features/entities/hooks/use-entities";
import { Loader2 } from "lucide-react";
import { useMemo } from "react";

/**
 * Where an entity is named in document text, grouped by file, newest first, each
 * row dropping down to the highlighted source. NER mentions only -- From/To/Cc
 * live in Connections, selector hits in Selectors. Paged; still "load more" for
 * an entity named across many documents.
 */
export function EntityMentionsByFile({
  entityId,
  emptyLabel,
}: {
  entityId: string;
  emptyLabel?: string;
}) {
  const { data, isPending, hasNextPage, fetchNextPage, isFetchingNextPage } =
    useEntityMentionsInfinite(entityId, { provenance: "text" });

  const mentions = useMemo(
    () => data?.pages.flatMap((p) => p.data) ?? [],
    [data]
  );
  const total = data?.pages[0]?.total ?? 0;

  if (isPending) {
    return <Loader2 size={16} className="animate-spin text-muted-foreground" />;
  }

  return (
    <div className="space-y-3">
      {total > 0 && (
        <p className="text-[11px] text-muted-foreground">
          Showing {mentions.length.toLocaleString()} of {total.toLocaleString()}
        </p>
      )}
      <MentionsByFile
        mentions={mentions}
        emptyLabel={emptyLabel ?? "Not named in any document text yet."}
      />
      {hasNextPage && (
        <div className="flex justify-center">
          <Button
            variant="ghost"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="text-[10px] uppercase tracking-widest text-primary"
          >
            {isFetchingNextPage && (
              <Loader2 size={12} className="mr-2 animate-spin" />
            )}
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
