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
  useDataset,
  useDatasetStats,
  useEnrichmentConfig,
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
import { ProgressTooltipBody } from "@/features/datasets/components/progress-tooltip-body";
import { ResolutionStage } from "@/features/datasets/components/resolution-stage";
import { EnrichmentRequestDialog } from "@/features/datasets/components/enrichment-request-dialog";
import { EstimateBadge } from "@/features/datasets/components/estimate-badge";
import { useDatasetRequestConfig } from "@/features/datasets/hooks/use-request-dataset";
import { RUN_STATUS_ICON } from "@/features/runs/components/run-status-icon";
import { RunStepsDialog } from "@/features/runs/components/run-steps-dialog";
import { StageFilesDialog } from "@/features/runs/components/stage-files-dialog";
import { StepMenu } from "@/features/runs/components/step-menu";
import { useRunPlanActions, useRunPlans } from "@/features/runs/hooks/use-run-plans";
import { ENTITY_RESOLUTION, STAGING } from "@/features/runs/types";
import {
  LIVE,
  WAITING,
  currentStepByType,
  stagingProgress,
  stepStateText,
  versionNote,
  type PlannedStep,
} from "@/features/runs/utils";
import { useIsAdmin } from "@/features/users/hooks/use-me";
import {
  allPrerequisites,
  sumEstimates,
  type EnrichmentEstimate,
  type RunDevice,
} from "@/features/datasets/request-types";
import type { EnrichmentProgress } from "@/features/datasets/types";
import { cn, formatCompactNumber, humanize } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import {
  AlertTriangle,
  Binary,
  CalendarClock,
  Check,
  ArrowUpRight,
  ChevronRight,
  FolderInput,
  GitBranch,
  Circle,
  CirclePause,
  Contact,
  FileArchive,
  FileText,
  Gauge,
  Image as ImageIcon,
  KeyRound,
  ListChecks,
  Loader2,
  MapPin,
  Network,
  Play,
  ScanFace,
  ScanText,
  Send,
  Signature,
  Sparkles,
  Table2,
  Users,
  UsersRound,
  Waypoints,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

const META: Record<string, { label: string; Icon: IconComponent }> = {
  archiveExtraction: { label: "Archive extraction", Icon: FileArchive },
  textExtraction: { label: "Text extraction", Icon: FileText },
  ocr: { label: "OCR", Icon: ScanText },
  textEmbedding: { label: "Text embedding", Icon: Binary },
  imageEmbedding: { label: "Image embedding", Icon: ImageIcon },
  exifLocation: { label: "Photo locations", Icon: MapPin },
  faceDetection: { label: "Face detection", Icon: ScanFace },
  faceMatching: { label: "Face matching", Icon: Users },
  faceClustering: { label: "Face clustering", Icon: UsersRound },
  contactExtraction: { label: "Contact extraction", Icon: Contact },
  selectorExtraction: { label: "Selector extraction", Icon: KeyRound },
  entityExtraction: { label: "Entity extraction", Icon: Network },
  relationshipExtraction: { label: "Relationship extraction", Icon: Waypoints },
  eventExtraction: { label: "Event extraction", Icon: CalendarClock },
  signatureExtraction: { label: "Signature extraction", Icon: Signature },
  tableExtraction: { label: "Table extraction", Icon: Table2 },
  textSummarization: { label: "Summaries", Icon: Sparkles },
};

const metaFor = (enrichmentType: string) =>
  META[enrichmentType] ?? {
    label: humanize(enrichmentType),
    Icon: Gauge,
  };

/** Display name of any plan step: an analytic, staging, or entity resolution. */
const labelFor = (stepType: string) =>
  stepType === STAGING
    ? "Staging"
    : stepType === ENTITY_RESOLUTION
      ? "Entity resolution"
      : metaFor(stepType).label;

/** A planned step that is waiting or running owns the row's status. */
const isActive = (planned: PlannedStep | undefined) =>
  !!planned && (LIVE.includes(planned.step.status) || WAITING.includes(planned.step.status));

/** Only analytics with a local model get a label; parsers and served-LLM passes (`na`) don't. */
const DEVICE_LABEL: Partial<Record<RunDevice, string>> = {
  cuda: "GPU",
  mps: "GPU",
  cpu: "CPU",
};

type StepState = "done" | "failed" | "running" | "waiting" | "not_run";

function deriveState(p: EnrichmentProgress | undefined): StepState {
  if (!p) return "not_run";
  if (p.isRunning) return "running";
  // Queued rows with no worker on them: an interrupted or stopped run, not progress.
  const outstanding = (p.counts.pending ?? 0) + (p.counts.processing ?? 0);
  if (outstanding > 0) return "waiting";
  // A step only reads as "failed" when nothing got through; a handful of bad
  // rows among many good ones is still done, surfaced via the failed count.
  if ((p.counts.failed ?? 0) > 0 && p.completed === 0) return "failed";
  return "done";
}

const STATE_ICON: Record<StepState, React.ReactNode> = {
  done: <Check className="size-3.5 text-primary" />,
  running: <Loader2 className="size-3.5 animate-spin text-primary" />,
  failed: <AlertTriangle className="size-3.5 text-destructive" />,
  waiting: <CirclePause className="size-3.5 text-muted-foreground" />,
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

/** Has work left that a request could ask for. */
const isRequestable = (row: Row) =>
  isApplicable(row) && deriveState(row.progress) !== "done";

/** A prerequisite needs no request: it's done or running, or this dataset has nothing for it to process. */
const isSatisfied = (row: Row | undefined) => {
  if (!row) return true;
  const state = deriveState(row.progress);
  return state === "done" || state === "running" || (!isApplicable(row) && !row.progress);
};

function Section({
  summary,
  issuesUrl,
  children,
}: {
  summary?: string;
  issuesUrl?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
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

/** First row of the pipeline: files loaded into the dataset, where from, and a crawl in progress. */
function StagingRow({
  datasetId,
  planned,
  isAdmin,
  onStageFiles,
}: {
  datasetId: string;
  planned?: PlannedStep;
  isAdmin: boolean;
  onStageFiles: () => void;
}) {
  const { data: dataset } = useDataset(datasetId);
  const { data: stats } = useDatasetStats(datasetId, {});
  const step = planned?.step;
  const isPlannedActive = isActive(planned);
  const isStaged = !!dataset?.dateStaged;
  const crawl = step ? stagingProgress(step) : null;
  const uri = step?.parameters.uri as string | undefined;
  const fileCount = stats?.totalFiles ?? 0;

  return (
    <li className="group/row py-2.5">
      <div className="flex items-center gap-3">
        <span className="size-4 shrink-0" />
        <span className="flex w-4 shrink-0 justify-center">
          {isPlannedActive && step
            ? RUN_STATUS_ICON[step.status]
            : isStaged
              ? STATE_ICON.done
              : STATE_ICON.not_run}
        </span>
        <span className="flex min-w-0 flex-1 items-center gap-2">
          <FolderInput className="size-3 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm text-foreground">Staging</span>
          {fileCount > 0 && (
            <span className="shrink-0 text-[11px] text-muted-foreground">
              {formatCompactNumber(fileCount)} files
            </span>
          )}
          {uri && (
            <span className="truncate font-mono text-[11px] text-muted-foreground" title={uri}>
              {uri}
            </span>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className={cn("text-[11px]", step?.status === "failed" ? "text-destructive" : "text-muted-foreground")}>
            {step && (isPlannedActive || step.status !== "completed")
              ? stepStateText(step, labelFor)
              : isStaged
                ? "Done"
                : "No files yet"}
          </span>
          <StepMenu step={step} label="Staging" isAdmin={isAdmin} onStageFiles={isAdmin ? onStageFiles : undefined} />
        </span>
      </div>
      {step && isPlannedActive && crawl && (
        <p className="mt-1 pl-14 text-[11px] text-muted-foreground">
          {formatCompactNumber(crawl.staged)} staged of {formatCompactNumber(crawl.found)} found
          {crawl.alreadyStaged > 0 && ` · ${formatCompactNumber(crawl.alreadyStaged)} already staged`}
          {!crawl.isListingDone && " · still listing"}
        </p>
      )}
    </li>
  );
}

export function EnrichmentPipeline({ datasetId }: { datasetId: string }) {
  const progressQuery = useEnrichmentProgress(datasetId);
  const estimatesQuery = useEnrichmentEstimates(datasetId);
  const { data: enrichmentConfig } = useEnrichmentConfig();
  const isAdmin = useIsAdmin();
  const { data: requestConfig } = useDatasetRequestConfig();
  const { data: plans } = useRunPlans(datasetId);
  const { create } = useRunPlanActions();
  const [failuresType, setFailuresType] = useState<string | null>(null);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [isRequestOpen, setIsRequestOpen] = useState(false);
  const [isStageOpen, setIsStageOpen] = useState(false);
  const issuesUrl = requestConfig?.issuesUrl;
  const current = currentStepByType(plans);
  const runNow = (stepType: string) => create.mutate({ datasetId, steps: [{ stepType }] });

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
  const rowByType = new Map(rows.map((r) => [r.enrichmentType, r]));
  const dependencies = enrichmentConfig?.dependencies ?? {};

  /** Prerequisites of `type` that are neither satisfied nor selected alongside it. */
  const missingFor = (type: string, chosen: ReadonlySet<string>) =>
    allPrerequisites(dependencies, type).filter(
      (dep) => !chosen.has(dep) && !isSatisfied(rowByType.get(dep))
    );

  /** Adds `types` plus their unmet, requestable prerequisites to the selection. */
  const selectWithPrerequisites = (types: string[]) => {
    const next = new Set(selected);
    for (const type of types) {
      next.add(type);
      for (const dep of missingFor(type, next)) {
        const depRow = rowByType.get(dep);
        if (depRow && isRequestable(depRow)) next.add(dep);
      }
    }
    setSelected(next);
  };

  const toggle = (row: Row, checked: boolean) => {
    if (checked) return selectWithPrerequisites([row.enrichmentType]);
    const next = new Set(selected);
    next.delete(row.enrichmentType);
    setSelected(next);
  };

  const missingByType = new Map(
    [...selected]
      .map((type) => [type, missingFor(type, selected)] as const)
      .filter(([, missing]) => missing.length > 0)
  );

  const selectedEstimates = estimates.items.filter((it) =>
    selected.has(it.enrichmentType)
  );
  const selectedTotal = sumEstimates(selectedEstimates);
  const applicableCount = rows.filter((r) => isApplicable(r) || r.progress).length;
  const states = rows.map((r) => deriveState(r.progress));
  const runningCount = states.filter((state) => state === "running").length;
  const failedCount = states.filter((state) => state === "failed").length;
  const plannedSteps = [...current.values()].map(({ step }) => step);
  const runningSteps = Math.max(runningCount, plannedSteps.filter((step) => LIVE.includes(step.status)).length);
  const queuedSteps = plannedSteps.filter((step) => step.status === "queued").length;
  const summary = [
    `${doneTypes.size} of ${applicableCount} done`,
    runningSteps > 0 && `${runningSteps} running`,
    queuedSteps > 0 && `${queuedSteps} queued`,
    failedCount > 0 && `${failedCount} failed`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Section summary={summary} issuesUrl={issuesUrl}>

      <ul className="divide-y divide-border/60">
        <StagingRow
          datasetId={datasetId}
          planned={current.get(STAGING)}
          isAdmin={isAdmin}
          onStageFiles={() => setIsStageOpen(true)}
        />
        {rows.map((row) => {
          const meta = metaFor(row.enrichmentType);
          const { estimate, progress } = row;
          const planned = current.get(row.enrichmentType);
          const state = deriveState(progress);
          const isPlannedActive = isActive(planned);
          const shownPlan =
            planned && (isPlannedActive || (state !== "done" && planned.step.status !== "completed"))
              ? planned
              : undefined;
          const note = planned ? versionNote(planned.step, planned.plan) : null;
          // Already-run analytics aren't requestable: a request asks for work that hasn't happened.
          const requestable = isRequestable(row) && !isPlannedActive;
          const directDeps = dependencies[row.enrichmentType] ?? [];
          const missing = missingByType.get(row.enrichmentType) ?? [];
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
              className={cn("group/row py-2.5", !isApplicable(row) && !progress && "opacity-60")}
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
                  {isPlannedActive && planned ? RUN_STATUS_ICON[planned.step.status] : STATE_ICON[state]}
                </span>
                <span className="flex min-w-0 flex-1 items-center gap-2">
                  <meta.Icon className="size-3 shrink-0 text-muted-foreground" />
                  <span className="truncate text-sm text-foreground">
                    {meta.label}
                  </span>
                  {directDeps.length > 0 && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          className={cn(
                            "inline-flex shrink-0 cursor-default items-center gap-1 rounded border px-1 text-[11px]",
                            missing.length
                              ? "border-destructive/50 text-destructive"
                              : "border-border text-muted-foreground"
                          )}
                        >
                          <Workflow className="size-3" />
                          {missing.length
                            ? `needs ${missing.map((t) => metaFor(t).label).join(", ")}`
                            : `${directDeps.length} ${directDeps.length === 1 ? "dependency" : "dependencies"}`}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent className="text-xs">
                        <p className="mb-1 font-medium">Runs after</p>
                        <ul className="space-y-0.5">
                          {directDeps.map((dep) => (
                            <li key={dep} className="flex items-center gap-1.5">
                              <span className="flex w-4 justify-center">
                                {STATE_ICON[deriveState(rowByType.get(dep)?.progress)]}
                              </span>
                              {metaFor(dep).label}
                              {selected.has(dep) && (
                                <span className="text-annotation">· selected</span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </TooltipContent>
                    </Tooltip>
                  )}
                  {deviceLabel && (
                    <span className="shrink-0 rounded border border-border px-1 font-mono text-[11px] text-muted-foreground">
                      {deviceLabel}
                    </span>
                  )}
                  {estimate?.eligible.estimable &&
                    estimate.eligible.unitCount > 0 && (
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {formatCompactNumber(estimate.eligible.unitCount)}{" "}
                        {humanize(estimate.eligible.unit)}
                      </span>
                    )}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {note && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <GitBranch className="size-3.5 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent className="text-xs">{note}</TooltipContent>
                    </Tooltip>
                  )}
                  {shownPlan && (
                    <span
                      className={cn(
                        "text-[11px]",
                        shownPlan.step.status === "failed" ? "text-destructive" : "text-muted-foreground"
                      )}
                    >
                      {stepStateText(shownPlan.step, labelFor)}
                    </span>
                  )}
                  {state === "running" && progress && !progress.stages?.length && (
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {Math.round(progress.progress * 100)}%
                    </span>
                  )}
                  {shownPlan ? null : state === "done" ? (
                    <span className="text-[11px] text-muted-foreground">Done</span>
                  ) : state === "waiting" ? (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="cursor-default text-[11px] text-muted-foreground">
                          Stopped · {formatCompactNumber(queued)} waiting
                        </span>
                      </TooltipTrigger>
                      <TooltipContent className="max-w-64 text-xs">
                        Nothing is processing these. The last run stopped before reaching them; re-run
                        the step to pick them up.
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    <EstimateBadge estimate={estimate} />
                  )}
                  <StepMenu
                    step={planned?.step}
                    label={meta.label}
                    isAdmin={isAdmin}
                    onRun={
                      isAdmin && requestable && missingFor(row.enrichmentType, new Set()).length === 0
                        ? () => runNow(row.enrichmentType)
                        : undefined
                    }
                  />
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
                      <ProgressTooltipBody
                        title={meta.label}
                        lines={[
                          `${formatCompactNumber(progress.completed)} done`,
                          ...(skipped > 0
                            ? [`${formatCompactNumber(skipped)} skipped (deliberately not processed)`]
                            : []),
                          ...(failed > 0 ? [`${formatCompactNumber(failed)} failed`] : []),
                          ...(queued > 0 ? [`${formatCompactNumber(queued)} queued`] : []),
                        ]}
                        skipReasons={progress.skipReasons}
                      />
                    </TooltipContent>
                  </Tooltip>
                  <p className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                    <span>{formatCompactNumber(progress.completed)} done</span>
                    {progress.dateLastRun && (
                      <span>· last run {new Date(progress.dateLastRun).toLocaleString()}</span>
                    )}
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
      <ResolutionStage
        datasetId={datasetId}
        planned={current.get(ENTITY_RESOLUTION)}
        menu={
          <StepMenu
            step={current.get(ENTITY_RESOLUTION)?.step}
            label="Entity resolution"
            isAdmin={isAdmin}
            onRun={
              isAdmin && !isActive(current.get(ENTITY_RESOLUTION)) ? () => runNow(ENTITY_RESOLUTION) : undefined
            }
          />
        }
      />

      {missingByType.size > 0 && (
        <Alert variant="destructive" className="mt-3">
          <AlertTriangle />
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {[...missingByType]
                .map(
                  ([type, missing]) =>
                    `${metaFor(type).label} needs ${missing.map((t) => metaFor(t).label).join(", ")}`
                )
                .join("; ")}{" "}
              to run first.
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => selectWithPrerequisites([...missingByType.keys()])}
            >
              Select dependencies
            </Button>
          </AlertDescription>
        </Alert>
      )}

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
            disabled={selected.size === 0 || missingByType.size > 0}
            className="gap-1.5"
          >
            {isAdmin ? <Play size={13} /> : <Send size={13} />}
            {isAdmin ? "Run selected" : "Request selected"}
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

      {isAdmin ? (
        <RunStepsDialog
          datasetId={datasetId}
          selected={selectedEstimates}
          labelFor={labelFor}
          isOpen={isRequestOpen}
          onOpenChange={setIsRequestOpen}
          onQueued={() => setSelected(new Set())}
        />
      ) : (
        <EnrichmentRequestDialog
          datasetId={datasetId}
          selected={selectedEstimates}
          labelFor={labelFor}
          isOpen={isRequestOpen}
          onOpenChange={setIsRequestOpen}
          onFiled={() => setSelected(new Set())}
        />
      )}
      {isAdmin && (
        <StageFilesDialog datasetId={datasetId} isOpen={isStageOpen} onOpenChange={setIsStageOpen} />
      )}
    </Section>
  );
}
