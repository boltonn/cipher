"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { formatDuration } from "@/features/datasets/request-types";
import { RUN_STATUS_ICON, RUN_STATUS_LABEL } from "@/features/runs/components/run-status-icon";
import { useRunPlanActions } from "@/features/runs/hooks/use-run-plans";
import type { CodeVersion, PlanRun } from "@/features/runs/types";
import { FINISHED, LIVE, ago, shortSha } from "@/features/runs/utils";
import { cn } from "@/lib/utils";
import { Copy, FileWarning, FolderInput, Info, MoreHorizontal, Play, RotateCw, Square } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

interface StepMenuProps {
  /** The step's current plan row, if it has ever been planned. */
  step?: PlanRun;
  label: string;
  isAdmin: boolean;
  /** Admin: queue just this step now (it has work left and nothing is waiting or running). */
  onRun?: () => void;
  /** Admin, staging only: open the stage-files dialog. */
  onStageFiles?: () => void;
  className?: string;
}

const copy = async (text: string, what: string) => {
  await navigator.clipboard.writeText(text);
  toast.success(`${what} copied`);
};

const version = (code: CodeVersion | null | undefined) =>
  code ? `${code.branch ?? "?"} @ ${shortSha(code.sha)}` : "—";

/** The `⋯` actions of one pipeline step: run / stop, where it runs, its error log. */
export function StepMenu({ step, label, isAdmin, onRun, onStageFiles, className }: StepMenuProps) {
  const { cancelRun, requeueRun } = useRunPlanActions();
  const [dialog, setDialog] = useState<"details" | "error" | null>(null);

  const isCancellable = !!step && (step.status === "queued" || step.status === "running");
  const isRerunnable = !!step && step.status !== "completed" && FINISHED.includes(step.status);
  const hasError = !!step?.errorMessage && (step.status === "failed" || step.status === "stopped");
  const adminItems = isAdmin && (isCancellable || isRerunnable || onRun || onStageFiles);

  if (!adminItems && !step) {
    return <span className={cn("size-7 shrink-0", className)} />;
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`${label} actions`}
            className={cn(
              "size-7 shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-foreground",
              "group-hover/row:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100",
              className
            )}
          >
            <MoreHorizontal className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          {adminItems && (
            <>
              <DropdownMenuLabel className="text-[11px] font-medium text-admin">Admin</DropdownMenuLabel>
              {onStageFiles && (
                <DropdownMenuItem onSelect={onStageFiles}>
                  <FolderInput /> Stage files…
                </DropdownMenuItem>
              )}
              {onRun && (
                <DropdownMenuItem onSelect={onRun}>
                  <Play /> Run now
                </DropdownMenuItem>
              )}
              {isRerunnable && (
                <DropdownMenuItem onSelect={() => requeueRun.mutate(step.id)}>
                  <RotateCw /> Run again
                </DropdownMenuItem>
              )}
              {isCancellable && (
                <DropdownMenuItem variant="destructive" onSelect={() => cancelRun.mutate(step.id)}>
                  <Square /> {step.status === "running" ? "Stop" : "Cancel"}
                </DropdownMenuItem>
              )}
              {step && <DropdownMenuSeparator />}
            </>
          )}
          {step && (
            <DropdownMenuItem onSelect={() => setDialog("details")}>
              <Info /> Details
            </DropdownMenuItem>
          )}
          {hasError && (
            <DropdownMenuItem onSelect={() => setDialog("error")}>
              <FileWarning /> Show error
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {step && (
        <Dialog open={dialog !== null} onOpenChange={(open) => !open && setDialog(null)}>
          <DialogContent className="sm:max-w-2xl [&>*]:min-w-0">
            {dialog === "error" ? <ErrorLog step={step} label={label} /> : <StepDetails step={step} label={label} />}
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{term}</dt>
      <dd className="min-w-0 text-foreground">{children}</dd>
    </>
  );
}

function CopyLine({ text, what }: { text: string; what: string }) {
  return (
    <div className="flex w-full min-w-0 items-center gap-2 rounded-md border border-border bg-muted/40 py-1 pr-1 pl-2.5">
      <code className="min-w-0 flex-1 truncate font-mono text-[11px]" title={text}>
        {text}
      </code>
      <Button variant="ghost" size="icon" className="size-6 shrink-0" aria-label={`Copy ${what}`} onClick={() => copy(text, what)}>
        <Copy className="size-3.5" />
      </Button>
    </div>
  );
}

/** Where a step runs and how to follow it on that machine. */
function StepDetails({ step, label }: { step: PlanRun; label: string }) {
  const process = step.process;
  const isLive = LIVE.includes(step.status);
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2 text-sm font-semibold">
          {RUN_STATUS_ICON[step.status]} {label} · {RUN_STATUS_LABEL[step.status]}
        </DialogTitle>
        <DialogDescription className="text-xs">
          A cipher worker on the host below runs the command as its own process and writes everything it
          prints to the log file there.
        </DialogDescription>
      </DialogHeader>
      <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-2 text-sm">
        <Row term="Host">
          {process ? `${process.host}${process.gpu != null ? ` · GPU ${process.gpu}` : ""}` : "Not started yet"}
        </Row>
        {process && (
          <>
            <Row term="Worker pid">{process.workerPid}</Row>
            <Row term="Step pid">{process.pid}</Row>
          </>
        )}
        <Row term="Started">{step.dateStarted ? ago(step.dateStarted) : "—"}</Row>
        {isLive && <Row term="Last heard">{ago(step.dateHeartbeat) || "—"}</Row>}
        {step.durationSeconds != null && <Row term="Took">{formatDuration(step.durationSeconds).replace(/^~/, "")}</Row>}
        <Row term="Code">{version(step.ranOn)}</Row>
      </dl>
      <div className="min-w-0 space-y-2">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Command</p>
        <CopyLine text={step.command} what="Command" />
        {process && (
          <>
            <p className="pt-2 text-[11px] uppercase tracking-wide text-muted-foreground">On {process.host}</p>
            <CopyLine text={`tail -f ${process.log}`} what="Log command" />
            {isLive && <CopyLine text={`ps -o pid,etime,args -g ${process.pid}`} what="ps command" />}
            <CopyLine text="cipher runs --here" what="Runs command" />
          </>
        )}
      </div>
    </>
  );
}

function ErrorLog({ step, label }: { step: PlanRun; label: string }) {
  return (
    <>
      <DialogHeader>
        <DialogTitle className="text-sm font-semibold">{label}: last lines of the log</DialogTitle>
        <DialogDescription className="text-xs">
          {[step.process?.host, ago(step.dateCompleted)].filter(Boolean).join(" · ")}
          {step.process && ` · full log: ${step.process.log}`}
        </DialogDescription>
      </DialogHeader>
      <pre className="max-h-[50vh] overflow-auto rounded-lg border border-border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
        {step.errorMessage}
      </pre>
      <DialogFooter>
        <Button variant="outline" size="sm" onClick={() => copy(step.errorMessage ?? "", "Log")}>
          <Copy /> Copy
        </Button>
      </DialogFooter>
    </>
  );
}
