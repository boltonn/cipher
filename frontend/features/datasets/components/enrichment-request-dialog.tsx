"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { EstimateBadge } from "@/features/datasets/components/estimate-badge";
import {
  useDatasetRequestConfig,
  useRequestEnrichment,
} from "@/features/datasets/hooks/use-request-dataset";
import {
  enrichmentRequestSchema,
  formatDuration,
  type EnrichmentEstimate,
} from "@/features/datasets/request-types";
import { ArrowUpRight, Check, Copy, Loader2 } from "lucide-react";
import { useState } from "react";

const FIELD_LABEL = "text-[11px] uppercase tracking-wide text-muted-foreground";

interface EnrichmentRequestDialogProps {
  datasetId: string;
  /** Selected analytics, in pipeline order; empty closes the dialog. */
  selected: EnrichmentEstimate[];
  labelFor: (enrichmentType: string) => string;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onFiled: () => void;
}

export function EnrichmentRequestDialog({
  isOpen,
  onOpenChange,
  ...props
}: EnrichmentRequestDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card border-border sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-sm font-semibold">
            Request enrichment
          </DialogTitle>
          <DialogDescription className="text-xs">
            Running analytics from the app isn&apos;t available yet, so this
            files a GitHub issue for whoever runs the pipeline. Each analytic
            runs over every eligible file in the dataset.
          </DialogDescription>
        </DialogHeader>
        {/* keyed by isOpen so each open starts from a clean form */}
        <EnrichmentRequestForm
          key={String(isOpen)}
          {...props}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function EnrichmentRequestForm({
  datasetId,
  selected,
  labelFor,
  onFiled,
  onDone,
}: Omit<EnrichmentRequestDialogProps, "isOpen" | "onOpenChange"> & {
  onDone: () => void;
}) {
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState<string>();
  const [copied, setCopied] = useState(false);
  const { data: config } = useDatasetRequestConfig();
  const requestEnrichment = useRequestEnrichment();
  const result = requestEnrichment.data;
  const canFile = !!config?.configured;

  const total = selected.reduce((sum, it) => sum + (it.estimateSeconds ?? 0), 0);

  const handleSubmit = () => {
    const parsed = enrichmentRequestSchema.safeParse({
      datasetId,
      analytics: selected.map((it) => ({
        enrichmentType: it.enrichmentType,
        parameters: {},
      })),
      note: note.trim() || undefined,
    });
    if (!parsed.success) {
      setNoteError(parsed.error.flatten().fieldErrors.note?.[0]);
      return;
    }
    setNoteError(undefined);
    requestEnrichment.mutate(parsed.data, {
      onSuccess: (data) => data.issueUrl && onFiled(),
    });
  };

  const handleCopy = async () => {
    if (!result) return;
    await navigator.clipboard.writeText(`# ${result.title}\n\n${result.body}`);
    setCopied(true);
  };

  if (result?.issueUrl) {
    return (
      <>
        <Alert>
          <Check />
          <AlertDescription>
            Filed as issue #{result.issueNumber}.{" "}
            <a
              href={result.issueUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-0.5 text-primary hover:underline"
            >
              Open on GitHub <ArrowUpRight size={12} />
            </a>
          </AlertDescription>
        </Alert>
        <DialogFooter>
          <Button onClick={onDone}>Done</Button>
        </DialogFooter>
      </>
    );
  }

  if (result) {
    return (
      <>
        <Alert>
          <AlertDescription>
            GitHub issue filing isn&apos;t configured on this backend
            (<code>GITHUB__*</code>). Copy the request below into an issue
            instead.
          </AlertDescription>
        </Alert>
        <Textarea
          readOnly
          value={result.body}
          className="min-h-56 bg-muted/40 border-border font-mono text-[11px]"
        />
        <DialogFooter>
          <Button variant="ghost" onClick={onDone} className="text-muted-foreground">
            Close
          </Button>
          <Button onClick={handleCopy} className="gap-2">
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? "Copied" : "Copy request"}
          </Button>
        </DialogFooter>
      </>
    );
  }

  return (
    <>
      <div className="space-y-4">
        <ul className="divide-y divide-border/60 rounded-lg border border-border">
          {selected.map((it) => (
            <li
              key={it.enrichmentType}
              className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
            >
              <span className="truncate">{labelFor(it.enrichmentType)}</span>
              <EstimateBadge estimate={{ ...it, progress: 0 }} />
            </li>
          ))}
          <li className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
            <span className="text-muted-foreground">Total (sequential)</span>
            <span className="font-medium tabular-nums">{formatDuration(total)}</span>
          </li>
        </ul>

        <Field data-invalid={!!noteError}>
          <FieldLabel htmlFor="enrichment-request-note" className={FIELD_LABEL}>
            Why (optional)
          </FieldLabel>
          <Textarea
            id="enrichment-request-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            aria-invalid={!!noteError}
            placeholder="e.g. need the scanned PDFs searchable for the review"
            className="bg-muted/40 border-border text-sm min-h-20"
          />
          <FieldError errors={noteError ? [{ message: noteError }] : undefined} />
        </Field>

        {requestEnrichment.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {(requestEnrichment.error as Error).message || "Request failed"}
            </AlertDescription>
          </Alert>
        )}
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onDone} className="text-muted-foreground">
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={requestEnrichment.isPending}
          className="gap-2"
        >
          {requestEnrichment.isPending && <Loader2 size={14} className="animate-spin" />}
          {canFile ? "File issue" : "Generate request"}
        </Button>
      </DialogFooter>
    </>
  );
}
