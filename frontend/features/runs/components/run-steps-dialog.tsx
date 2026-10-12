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
import { EstimateBadge } from "@/features/datasets/components/estimate-badge";
import { sumEstimates, type EnrichmentEstimate } from "@/features/datasets/request-types";
import { useRunPlanActions } from "@/features/runs/hooks/use-run-plans";
import { Loader2 } from "lucide-react";

interface RunStepsDialogProps {
  datasetId: string;
  /** Selected analytics, in pipeline order. */
  selected: EnrichmentEstimate[];
  labelFor: (enrichmentType: string) => string;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onQueued: () => void;
}

/** Admin: confirm the selected analytics and queue them for the workers. */
export function RunStepsDialog({ datasetId, selected, labelFor, isOpen, onOpenChange, onQueued }: RunStepsDialogProps) {
  const { create } = useRunPlanActions();

  const queue = () =>
    create.mutate(
      { datasetId, steps: selected.map((it) => ({ stepType: it.enrichmentType })) },
      {
        onSuccess: () => {
          onQueued();
          onOpenChange(false);
        },
      }
    );

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card border-border sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-white tracking-wide uppercase text-xs font-semibold">Run analytics</DialogTitle>
          <DialogDescription className="text-xs">
            Queued for the workers in pipeline order; each step starts when the steps it needs are done.
          </DialogDescription>
        </DialogHeader>
        <ul className="divide-y divide-border/60 rounded-lg border border-border">
          {selected.map((it) => (
            <li key={it.enrichmentType} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <span className="truncate">{labelFor(it.enrichmentType)}</span>
              <EstimateBadge estimate={{ ...it, progress: 0 }} />
            </li>
          ))}
          <li className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
            <span className="text-muted-foreground">Total (one after another)</span>
            <span className="font-medium tabular-nums">
              {sumEstimates(selected.map((it) => ({ ...it, progress: 0 })))}
            </span>
          </li>
        </ul>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-muted-foreground">
            Cancel
          </Button>
          <Button onClick={queue} disabled={create.isPending}>
            {create.isPending && <Loader2 className="animate-spin" />}
            Queue {selected.length} {selected.length === 1 ? "step" : "steps"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
