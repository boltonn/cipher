"use client";

import { Button } from "@/components/ui/button";
import { useFileSummary, useSummarizeFile } from "@/features/files/api";
import { cn } from "@/lib/utils";
import { isAxiosError } from "axios";
import { formatDistanceToNow } from "date-fns";
import { Loader2, RefreshCw, Sparkles } from "lucide-react";

/**
 * A file's AI summary. Summaries are written on request (one LLM call, ~20s) and kept as a
 * searchable summary chunk shared by identical files, so most files show the button rather than a summary.
 */
export function FileSummary({ fileId, className }: { fileId: string; className?: string }) {
  const { data: summary } = useFileSummary(fileId);
  const summarize = useSummarizeFile(fileId);
  const nothingToRead = isAxiosError(summarize.error) && summarize.error.response?.status === 422;

  return (
    <section className={cn("space-y-2 rounded-xl border border-border/50 bg-black/40 p-4", className)}>
      <div className="flex items-center gap-2">
        <Sparkles size={14} className="text-annotation" />
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-foreground">Summary</h4>
        {summary && !summarize.isPending && (
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto h-6 gap-1 px-2 text-[11px] text-muted-foreground"
            onClick={() => summarize.mutate(true)}
          >
            <RefreshCw size={11} /> Regenerate
          </Button>
        )}
      </div>

      {summarize.isPending ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 size={12} className="animate-spin" /> Summarizing… this can take ~20 seconds.
        </p>
      ) : summary ? (
        <>
          <p className="text-xs leading-relaxed text-foreground">{summary.text}</p>
          <p className="text-[11px] text-annotation/80">
            AI · {summary.generatedBy}
            {` · ${formatDistanceToNow(new Date(summary.dateCreated), { addSuffix: true })}`}
          </p>
        </>
      ) : (
        <div className="flex items-center gap-3">
          <p className="text-[11px] text-muted-foreground">
            {nothingToRead
              ? "Nothing to summarize yet — extract its text or map the table first."
              : summarize.isError
                ? "Couldn’t summarize — try again."
                : "Not summarized yet."}
          </p>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto h-8 gap-1.5 border-annotation/40 text-xs text-annotation hover:bg-annotation/10 hover:text-annotation"
            onClick={() => summarize.mutate(false)}
          >
            <Sparkles size={12} /> Summarize
          </Button>
        </div>
      )}
    </section>
  );
}
