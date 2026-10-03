"use client";

import { CopyableId } from "@/components/copyable-id";
import { Pagination } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useEnrichmentFailures } from "@/features/datasets/api";
import type { FailedEnrichment } from "@/features/datasets/types";
import { useFile } from "@/features/files/api";
import { FileViewerDialog } from "@/features/files/components/file-viewer-dialog";
import { cn, formatBytes, formatCompactNumber } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import {
  AlertTriangle,
  Eye,
  Loader2,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { useState } from "react";

const PAGE_SIZE = 25;
const NO_MESSAGE = "(no message recorded)";

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
  const [pageState, setPageState] = useState({ enrichmentType, page: 1 });
  const page = pageState.enrichmentType === enrichmentType ? pageState.page : 1;
  const [viewingFileId, setViewingFileId] = useState<string | null>(null);

  const { data, isPending, isFetching, isError } = useEnrichmentFailures(
    datasetId,
    enrichmentType,
    { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }
  );
  const { data: viewingFile } = useFile(viewingFileId ?? undefined);

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

        {data && data.total === 0 && (
          <p className="py-8 text-xs text-muted-foreground">
            No failed rows found.
          </p>
        )}

        {data && data.total > 0 && (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
            {data.reasons.length > 1 && (
              <div className="flex max-h-32 min-w-0 shrink-0 flex-col gap-1.5 overflow-y-auto rounded-lg border border-border bg-muted/40 p-3">
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
                      {reason.errorMessage ?? NO_MESSAGE}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <div
              className={cn(
                "flex min-h-0 min-w-0 flex-1 flex-col gap-2 overflow-y-auto pr-1",
                isFetching && "opacity-60"
              )}
            >
              {data.items.map((item) => (
                <FailedEnrichmentRow
                  key={item.id}
                  item={item}
                  onView={() => setViewingFileId(item.enrichableId)}
                />
              ))}
            </div>

            <div className="flex shrink-0 justify-end">
              {data.total > PAGE_SIZE && (
                <Pagination
                  variant="compact"
                  showRange
                  currentPage={page}
                  totalItems={data.total}
                  itemsPerPage={PAGE_SIZE}
                  isLoading={isFetching}
                  onPageChange={(next) =>
                    setPageState({ enrichmentType, page: next })
                  }
                />
              )}
            </div>
          </div>
        )}
      </DialogContent>

      <FileViewerDialog
        file={viewingFile ? { ...viewingFile, type: "file" } : null}
        isOpen={!!viewingFileId && !!viewingFile}
        onOpenChange={(open) => !open && setViewingFileId(null)}
      />
    </Dialog>
  );
}

function FailedEnrichmentRow({
  item,
  onView,
}: {
  item: FailedEnrichment;
  onView: () => void;
}) {
  return (
    <div className="min-w-0 shrink-0 rounded-lg border border-border bg-muted/30 p-3">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <span className="min-w-0 truncate font-mono text-xs text-foreground">
          {item.filename}
        </span>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-[11px] text-muted-foreground">
            {formatDistanceToNow(new Date(item.dateUpdated), {
              addSuffix: true,
            })}
          </span>
          <Button variant="ghost" size="xs" onClick={onView}>
            <Eye />
            View file
          </Button>
        </div>
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        {item.filetype} · {item.filetypeGroup} · {item.mimeType} ·{" "}
        {formatBytes(item.size)}
        {item.retryCount > 0 &&
          ` · ${item.retryCount} retr${item.retryCount === 1 ? "y" : "ies"}`}
      </p>
      <CopyableId id={item.path} label="Path" className="mt-1 w-full" />
      <CopyableId id={item.enrichableId} label="File ID" className="w-full" />
      <pre className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-background/60 p-2 font-mono text-[11px] text-destructive [overflow-wrap:anywhere]">
        {item.errorMessage ?? NO_MESSAGE}
      </pre>
    </div>
  );
}
