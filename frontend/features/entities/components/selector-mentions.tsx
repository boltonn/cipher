"use client";

import { Button } from "@/components/ui/button";
import { MentionsByFile } from "@/features/entities/components/mentions-by-file";
import { useSelectorMentions } from "@/features/entities/hooks/use-entities";
import { Loader2 } from "lucide-react";
import { useMemo } from "react";

/**
 * Every mention carrying `normalizedValue` -- across all datasets and whether or
 * not it has been resolved to an entity. Lets a linked selector show where its
 * value already appears in the corpus. Paginated because it can be many.
 */
export function SelectorMentions({
  normalizedValue,
  selectorType,
}: {
  normalizedValue: string | null;
  selectorType?: string | null;
}) {
  const {
    data,
    isPending,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useSelectorMentions(normalizedValue, selectorType);

  const mentions = useMemo(
    () => data?.pages.flatMap((p) => p.data) ?? [],
    [data]
  );
  const total = data?.pages[0]?.total ?? 0;

  if (isPending) {
    return <Loader2 size={16} className="animate-spin text-muted-foreground" />;
  }

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-muted-foreground">
        {total
          ? `${total} mention${total === 1 ? "" : "s"} of this value in the corpus`
          : "This value does not appear in any extracted text or fields yet."}
      </p>
      {mentions.length > 0 && (
        <MentionsByFile mentions={mentions} />
      )}
      {hasNextPage && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
          className="text-xs text-primary"
        >
          {isFetchingNextPage && (
            <Loader2 size={12} className="mr-2 animate-spin" />
          )}
          Load more
        </Button>
      )}
    </div>
  );
}
