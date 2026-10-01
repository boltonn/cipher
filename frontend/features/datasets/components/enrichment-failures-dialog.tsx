"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useEnrichmentFailures } from "@/features/datasets/api";
import { cn, formatCompactNumber } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import { AlertTriangle, Loader2, Maximize2, Minimize2 } from "lucide-react";
import { useState } from "react";

interface EnrichmentFailuresDialogProps {
  datasetId: string;
  /** The analytic to inspect; `null` closes the dialog. */
  enrichmentType: string | null;
  label: string;
  onClose: () => void;
}

export function EnrichmentFailuresDialog({
  datasetId,
  enrichmentType,
  label,
  onClose,
}: EnrichmentFailuresDialogProps) {
  const [expanded, setExpanded] = useState(false);
  const { data, isPending, isError } = useEnrichmentFailures(
    datasetId,
    enrichmentType
  );

  return (
    <Dialog open={!!enrichmentType} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className={cn(
          "flex flex-col overflow-hidden border-border bg-card",
          expanded
            ? "h-[90vh] w-[calc(100%-2rem)] sm:max-w-[95vw]"
            : "max-h-[85vh] sm:max-w-3xl"
        )}
      >
        <DialogHeader className="pr-16">
          <DialogTitle className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-destructive">
            <AlertTriangle size={14} />
            {label} — failures
          </DialogTitle>
          <DialogDescription>
            {data
              ? `${formatCompactNumber(data.total)} row${data.total === 1 ? "" : "s"} failed for this analytic.`
              : "Per-file error detail for this analytic."}
          </DialogDescription>
        </DialogHeader>

        <Button
          variant="ghost"
          size="icon-sm"
          className="absolute right-9 top-2"
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? <Minimize2 /> : <Maximize2 />}
          <span className="sr-only">
            {expanded ? "Collapse dialog" : "Expand dialog"}
          </span>
        </Button>

        {isPending && (
          <div className="flex items-center gap-2 py-8 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading failures…
          </div>
        )}

        {isError && (
          <p className="py-8 text-xs text-muted-foreground">
            Could not load failures (the backend may not support this yet).
          </p>
        )}

        {data && data.items.length === 0 && (
          <p className="py-8 text-xs text-muted-foreground">
            No failed rows found.
          </p>
        )}

        {data && data.items.length > 0 && (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
            {data.reasons.length > 1 && (
              <div className="flex min-w-0 flex-col gap-1.5 rounded-lg border border-border bg-muted/40 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Reasons
                </p>
                {data.reasons.map((reason, index) => (
                  <div
                    key={index}
                    className="flex min-w-0 items-start gap-2 text-[11px]"
                  >
                    <span className="shrink-0 font-mono text-destructive">
                      {formatCompactNumber(reason.count)}×
                    </span>
                    <span className="min-w-0 flex-1 font-mono text-muted-foreground [overflow-wrap:anywhere]">
                      {reason.errorMessage ?? "(no message recorded)"}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <ScrollArea className="min-h-0 min-w-0 flex-1 pr-3">
              <div className="flex flex-col gap-2">
                {data.items.map((item) => (
                  <div
                    key={item.id}
                    className="min-w-0 rounded-lg border border-border bg-muted/30 p-3"
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="truncate font-mono text-xs text-foreground">
                        {item.filename}
                      </span>
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {formatDistanceToNow(new Date(item.dateUpdated), {
                          addSuffix: true,
                        })}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px] text-muted-foreground/70">
                      {item.path}
                    </p>
                    <pre className="mt-2 whitespace-pre-wrap rounded bg-background/60 p-2 font-mono text-[11px] text-destructive [overflow-wrap:anywhere]">
                      {item.errorMessage ?? "(no message recorded)"}
                    </pre>
                    {item.retryCount > 0 && (
                      <p className="mt-1.5 text-[11px] text-muted-foreground">
                        {item.retryCount} retr{item.retryCount === 1 ? "y" : "ies"}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </ScrollArea>

            {data.total > data.returned && (
              <p className="text-[11px] text-muted-foreground">
                Showing the most recent {formatCompactNumber(data.returned)} of{" "}
                {formatCompactNumber(data.total)} failures.
              </p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
