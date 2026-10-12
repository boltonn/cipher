"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { formatDistanceToNow, parseISO } from "date-fns";
import { RefreshCw, Sparkles } from "lucide-react";
import { useDatasetBrief, useRegenerateBrief } from "../api";

interface DatasetBriefCardProps {
  datasetIds: string[];
  enabled?: boolean;
  onSearch: (query: string) => void;
}

/** The saved AI read of a dataset profile plus starting searches; hidden when the model is unavailable. */
export function DatasetBriefCard({ datasetIds, enabled = true, onSearch }: DatasetBriefCardProps) {
  const { data: brief, isPending, isError } = useDatasetBrief(datasetIds, enabled);
  const regenerate = useRegenerateBrief(datasetIds);
  if (isError || !enabled) return null;

  return (
    <section className="rounded-xl border border-annotation/30 bg-annotation/5 p-4">
      <div className="mb-2 flex items-center gap-1.5 text-xs">
        <Sparkles className="size-3.5 text-annotation" />
        <span className="font-medium text-annotation">AI overview of these numbers</span>
        {brief?.dateGenerated && (
          <span className="text-muted-foreground">
            · written {formatDistanceToNow(parseISO(brief.dateGenerated), { addSuffix: true })}
          </span>
        )}
        {brief?.isOutdated && <span className="text-muted-foreground">· dataset changed since</span>}
        {brief && (
          <button
            type="button"
            onClick={() => regenerate.mutate()}
            disabled={regenerate.isPending}
            className="ml-auto inline-flex h-7 items-center gap-1 rounded-md px-2 text-muted-foreground hover:bg-annotation/10 hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw className={cn("size-3.5", regenerate.isPending && "animate-spin")} />
            {regenerate.isPending ? "Regenerating…" : "Regenerate"}
          </button>
        )}
      </div>
      {isPending || !brief ? (
        <>
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="mt-2 h-4 w-2/3" />
        </>
      ) : (
        <>
          <p className="text-sm leading-relaxed text-foreground">{brief.summary}</p>
          {brief.suggestedSearches.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Try:</span>
              {brief.suggestedSearches.map((query) => (
                <button
                  key={query}
                  type="button"
                  onClick={() => onSearch(query)}
                  className="inline-flex h-7 items-center rounded-full border border-annotation/30 px-2.5 text-xs text-foreground hover:bg-annotation/10"
                >
                  {query}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
