"use client";

import { Button } from "@/components/ui/button";
import { MentionsByFile } from "@/features/entities/components/mentions-by-file";
import { useEntityMentionsInfinite } from "@/features/entities/hooks/use-entities";
import { Loader2 } from "lucide-react";
import { useMemo } from "react";

/**
 * Mentions of an entity grouped by the file they appear in, newest first, each
 * expanding to the highlighted source text. Shared by the entity and person
 * dossier pages; resolves the dataset per file so it works for dataset-agnostic
 * bridge entities too. Paged -- a hub entity can have thousands of mentions.
 */
export function EntityMentionsByFile({
  entityId,
  emptyLabel,
}: {
  entityId: string;
  emptyLabel?: string;
}) {
  const {
    data,
    isPending,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useEntityMentionsInfinite(entityId);

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
          Showing {mentions.length} of {total}
        </p>
      )}
      <MentionsByFile
        mentions={mentions}
        emptyLabel={emptyLabel ?? "No mentions recorded yet."}
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
