"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  useEnrichmentEstimates,
  useEnrichmentProgress,
} from "@/features/datasets/api";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EnrichmentFailuresDialog } from "@/features/datasets/components/enrichment-failures-dialog";
import { EnrichmentStages } from "@/features/datasets/components/enrichment-stages";
import { EnrichmentRequestDialog } from "@/features/datasets/components/enrichment-request-dialog";
import { EstimateBadge } from "@/features/datasets/components/estimate-badge";
import { useDatasetRequestConfig } from "@/features/datasets/hooks/use-request-dataset";
import {
  sumEstimates,
  type EnrichmentEstimate,
  type RunDevice,
} from "@/features/datasets/request-types";
import type { EnrichmentProgress } from "@/features/datasets/types";
import { cn, formatCompactNumber } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import {
  AlertTriangle,
  ArrowUpRight,
  Binary,
  CalendarClock,
  Check,
  ChevronRight,
  Circle,
  Contact,
  FileText,
  Gauge,
  Image as ImageIcon,
  Info,
  KeyRound,
  ListChecks,
  Loader2,
  MapPin,
  Network,
  ScanFace,
  ScanText,
  Send,
  Users,
  UsersRound,
  Waypoints,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

const META: Record<string, { label: string; Icon: IconComponent }> = {
  text_extraction: { label: "Text extraction", Icon: FileText },
  ocr: { label: "OCR", Icon: ScanText },
  text_embedding: { label: "Text embedding", Icon: Binary },
  image_embedding: { label: "Image embedding", Icon: ImageIcon },
  exif_location: { label: "Photo locations", Icon: MapPin },
  face_detection: { label: "Face detection", Icon: ScanFace },
  face_matching: { label: "Face matching", Icon: Users },
  face_clustering: { label: "Face clustering", Icon: UsersRound },
  contact_extraction: { label: "Contact extraction", Icon: Contact },
  selector_extraction: { label: "Selector extraction", Icon: KeyRound },
  entity_extraction: { label: "Entity extraction", Icon: Network },
  relationship_extraction: { label: "Relationship extraction", Icon: Waypoints },
  event_extraction: { label: "Event extraction", Icon: CalendarClock },
};

const metaFor = (enrichmentType: string) =>
  META[enrichmentType] ?? {
    label: enrichmentType.replace(/_/g, " "),
    Icon: Gauge,
  };

/** Only analytics with a local model get a label; parsers and served-LLM passes (`na`) don't. */
const DEVICE_LABEL: Partial<Record<RunDevice, string>> = {
  cuda: "GPU",
  mps: "GPU",
  cpu: "CPU",
};

type StepState = "done" | "failed" | "running" | "not_run";

function deriveState(p: EnrichmentProgress | undefined): StepState {
  if (!p) return "not_run";
  const outstanding = (p.counts.pending ?? 0) + (p.counts.processing ?? 0);
  if (outstanding > 0) return "running";
  // A step only reads as "failed" when nothing got through; a handful of bad
  // rows among many good ones is still done, surfaced via the failed count.
  if ((p.counts.failed ?? 0) > 0 && p.completed === 0) return "failed";
  return "done";
}

const STATE_ICON: Record<StepState, React.ReactNode> = {
  done: <Check className="size-3.5 text-primary" />,
  running: <Loader2 className="size-3.5 animate-spin text-primary" />,
  failed: <AlertTriangle className="size-3.5 text-destructive" />,
  not_run: <Circle className="size-3 text-muted-foreground/50" />,
};

interface Row {
  enrichmentType: string;
  estimate?: EnrichmentEstimate;
  progress?: EnrichmentProgress;
}

/** Estimates list every analytic in pipeline order; progress-only types are appended. */
function mergeRows(
  estimates: EnrichmentEstimate[],
  progress: EnrichmentProgress[]
): Row[] {
  const progressByType = new Map(progress.map((p) => [p.enrichmentType, p]));
  const rows: Row[] = estimates.map((estimate) => ({
    enrichmentType: estimate.enrichmentType,
    estimate,
    progress: progressByType.get(estimate.enrichmentType),
  }));
  const known = new Set(rows.map((r) => r.enrichmentType));
  for (const p of progress) {
    if (!known.has(p.enrichmentType)) {
      rows.push({ enrichmentType: p.enrichmentType, progress: p });
    }
  }
  return rows;
}

/** The dataset has something for this analytic to process (or it isn't sized by the file inventory). */
const isApplicable = (row: Row) =>
  !!row.estimate &&
  (!row.estimate.eligible.estimable || row.estimate.eligible.unitCount > 0);

function Section({
  summary,
  issuesUrl,
  children,
}: {
  summary?: string;
  issuesUrl?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="mt-6 rounded-2xl border border-border bg-muted/40 p-6 backdrop-blur-2xl"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CollapsibleTrigger className="group flex items-center gap-2 text-muted-foreground hover:text-foreground">
          <ChevronRight className="size-3.5 transition-transform group-data-[state=open]:rotate-90" />
          <ListChecks size={14} className="text-primary" />
          <h2 className="text-[11px] font-semibold uppercase tracking-wide">
            Enrichment pipeline
          </h2>
          {summary && (
            <span className="text-[11px] font-normal text-muted-foreground">
              · {summary}
            </span>
          )}
        </CollapsibleTrigger>
        <span className="flex items-center gap-4 text-[11px] font-medium">
          <Link href="/docs#analytics" className="text-primary hover:underline">
            Available analytics
          </Link>
          {issuesUrl && (
            <a
              href={issuesUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-0.5 text-primary hover:underline"
            >
              Open requests <ArrowUpRight size={12} />
            </a>
          )}
        </span>
      </div>
      <CollapsibleContent className="mt-4">{children}</CollapsibleContent>
    </Collapsible>
  );
}

export function EnrichmentPipeline({ datasetId }: { datasetId: string }) {
  const progressQuery = useEnrichmentProgress(datasetId);
  const estimatesQuery = useEnrichmentEstimates(datasetId);
  const { data: requestConfig } = useDatasetRequestConfig();
  const [failuresType, setFailuresType] = useState<string | null>(null);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [isRequestOpen, setIsRequestOpen] = useState(false);

  const issuesUrl = requestConfig?.issuesUrl;

  if (progressQuery.isError || estimatesQuery.isError) {
    return (
      <Section issuesUrl={issuesUrl}>
        <p className="py-2 text-xs text-destructive">
          Couldn&apos;t load enrichment progress -- the backend request failed.
        </p>
      </Section>
    );
  }

  if (progressQuery.isPending || estimatesQuery.isPending) {
    return (
      <Section issuesUrl={issuesUrl}>
        <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading pipeline…
        </div>
      </Section>
    );
  }

  const estimates = estimatesQuery.data;
  const rows = mergeRows(estimates.items, progressQuery.data);
  const doneTypes = new Set(
    rows.filter((r) => deriveState(r.progress) === "done").map((r) => r.enrichmentType)
  );

  const toggle = (row: Row, checked: boolean) => {
    const next = new Set(selected);
    if (!checked) {
      next.delete(row.enrichmentType);
    } else {
      next.add(row.enrichmentType);
      // Pull in unfinished prerequisites so the request is runnable as filed.
      for (const prerequisite of row.estimate?.prerequisites ?? []) {
        if (!doneTypes.has(prerequisite)) {
          next.add(prerequisite);
        }
      }
    }
    setSelected(next);
  };

  const selectedEstimates = estimates.items.filter((it) =>
    selected.has(it.enrichmentType)
  );
  const selectedTotal = sumEstimates(selectedEstimates);
  const applicableCount = rows.filter((r) => isApplicable(r) || r.progress).length;
  const summary = `${doneTypes.size} of ${applicableCount} done`;

  return (
    <Section summary={summary} issuesUrl={issuesUrl}>

      {!estimates.isStaged && (
        <Alert className="mb-3">
          <Info />
          <AlertDescription>
            This dataset isn&apos;t staged yet (no files loaded &amp; typed).
            Estimates appear once it is.
          </AlertDescription>
        </Alert>
      )}

      <ul className="divide-y divide-border/60">
        {rows.map((row) => {
          const meta = metaFor(row.enrichmentType);
          const { estimate, progress } = row;
          const state = deriveState(progress);
          // Already-run analytics aren't requestable: a request asks for work that hasn't happened.
          const requestable = isApplicable(row) && state !== "done";
          const failed = progress?.counts.failed ?? 0;
          // Skipped rows were deliberately not processed (a gate, an unreadable image): resolved, not outstanding.
          const skipped = progress?.counts.skipped ?? 0;
          const queued =
            (progress?.counts.pending ?? 0) + (progress?.counts.processing ?? 0);
          const completedPct = progress?.total
            ? (progress.completed / progress.total) * 100
            : 0;
          const failedPct = progress?.total ? (failed / progress.total) * 100 : 0;
          const skippedPct = progress?.total ? (skipped / progress.total) * 100 : 0;
          const deviceLabel =
            estimate && state !== "done" ? DEVICE_LABEL[estimate.device] : undefined;

          return (
            <li
              key={row.enrichmentType}
              className={cn("py-2.5", !isApplicable(row) && !progress && "opacity-60")}
            >
              <div className="flex items-center gap-3">
                <Checkbox
                  aria-label={`Request ${meta.label}`}
                  checked={selected.has(row.enrichmentType)}
                  onCheckedChange={(checked) => toggle(row, checked === true)}
                  disabled={!requestable}
                  className={cn(!requestable && "invisible")}
                />
                <span className="flex w-4 shrink-0 justify-center">
                  {STATE_ICON[state]}
                </span>
                <span className="flex min-w-0 flex-1 items-center gap-2">
                  <meta.Icon className="size-3 shrink-0 text-muted-foreground" />
                  <span className="truncate text-sm text-foreground">
                    {meta.label}
                  </span>
                  {deviceLabel && (
                    <span className="shrink-0 rounded border border-border px-1 font-mono text-[11px] text-muted-foreground">
                      {deviceLabel}
                    </span>
                  )}
                  {estimate?.eligible.estimable &&
                    estimate.eligible.unitCount > 0 && (
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {formatCompactNumber(estimate.eligible.unitCount)}{" "}
                        {estimate.eligible.unit.replace(/_/g, " ")}
                      </span>
                    )}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {state === "running" && progress && !progress.stages?.length && (
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {Math.round(progress.progress * 100)}%
                    </span>
                  )}
                  {state === "done" ? (
                    <span className="text-[11px] text-muted-foreground">Done</span>
                  ) : (
                    <EstimateBadge estimate={estimate} />
                  )}
                </span>
              </div>

              {!!progress?.stages?.length && (
                <EnrichmentStages
                  stages={progress.stages}
                  onShowFailures={() => setFailuresType(row.enrichmentType)}
                />
              )}
              {progress && !progress.stages?.length && (
                <div className="mt-1.5 pl-14">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex h-2 w-full cursor-default items-center">
                        <div className="flex h-1 w-full overflow-hidden rounded-full bg-border">
                          <div
                            className="h-full bg-primary transition-all"
                            style={{
                              width: `${progress.completed > 0 ? Math.max(completedPct, 2) : 0}%`,
                            }}
                          />
                          <div
                            className="h-full bg-muted-foreground/40 transition-all"
                            style={{ width: `${skipped > 0 ? Math.max(skippedPct, 2) : 0}%` }}
                          />
                          <div
                            className="h-full bg-destructive/70 transition-all"
                            style={{
                              width: `${failed > 0 ? Math.max(failedPct, 2) : 0}%`,
                            }}
                          />
                        </div>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent className="text-xs">
                      <p>{formatCompactNumber(progress.completed)} done</p>
                      {skipped > 0 && (
                        <p>
                          {formatCompactNumber(skipped)} skipped: deliberately not processed
                          (filtered out by a gate, or nothing to read)
                        </p>
                      )}
                      {failed > 0 && <p>{formatCompactNumber(failed)} failed</p>}
                      {queued > 0 && <p>{formatCompactNumber(queued)} queued</p>}
                    </TooltipContent>
                  </Tooltip>
                  <p className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                    <span>{formatCompactNumber(progress.completed)} done</span>
                    {skipped > 0 && (
                      <span>· {formatCompactNumber(skipped)} skipped</span>
                    )}
                    {failed > 0 && (
                      <button
                        type="button"
                        onClick={() => setFailuresType(row.enrichmentType)}
                        className="text-destructive underline-offset-2 hover:underline"
                      >
                        · {formatCompactNumber(failed)} failed
                      </button>
                    )}
                    {queued > 0 && (
                      <span>· {formatCompactNumber(queued)} queued</span>
                    )}
                    <span className="text-muted-foreground/60">
                      · {formatCompactNumber(progress.total)} total
                    </span>
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-3 text-sm">
        {selected.size > 0 ? (
          <span className="text-annotation">
            <span className="font-medium tabular-nums">
              {selectedTotal}
            </span>{" "}
            for {selected.size} selected{" "}
            <span className="text-annotation/60">(sequential)</span>
          </span>
        ) : (
          <span />
        )}
        <span className="flex items-center gap-3">
          <Button
            size="sm"
            onClick={() => setIsRequestOpen(true)}
            disabled={selected.size === 0}
            className="gap-1.5"
          >
            <Send size={13} />
            Request enrichment
          </Button>
        </span>
      </div>

      {failuresType && (
        <EnrichmentFailuresDialog
          datasetId={datasetId}
          enrichmentType={failuresType}
          label={metaFor(failuresType).label}
          onClose={() => setFailuresType(null)}
        />
      )}

      <EnrichmentRequestDialog
        datasetId={datasetId}
        selected={selectedEstimates}
        labelFor={(type) => metaFor(type).label}
        isOpen={isRequestOpen}
        onOpenChange={setIsRequestOpen}
        onFiled={() => setSelected(new Set())}
      />
    </Section>
  );
}
