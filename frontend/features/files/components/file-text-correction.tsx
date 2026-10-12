"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { humanize } from "@/lib/utils";
import { ArrowRight, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useCorrectFileText } from "../api";
import type { CorrectedMention, TextCorrectionSummary } from "../types";

/**
 * Edit a file's OCR text in place (admins). Saving goes through a review: the backend's dry run
 * says which marked names keep their place, which take the corrected spelling and which are
 * gone. Nothing is re-run unless the admin ticks steps to redo.
 */
export function FileTextCorrection({
  fileId,
  text,
  onDone,
}: {
  fileId: string;
  text: string;
  onDone: () => void;
}) {
  const [draft, setDraft] = useState(text);
  const [review, setReview] = useState<TextCorrectionSummary | null>(null);
  const [rerun, setRerun] = useState<string[]>([]);
  const correct = useCorrectFileText(fileId);
  const isChanged = draft !== text;
  const isRunning = (review?.running.length ?? 0) > 0;

  const openReview = () =>
    correct.mutate(
      { content: draft, dryRun: true },
      {
        onSuccess: (summary) => {
          setRerun([]);
          setReview(summary);
        },
      }
    );

  const save = () =>
    correct.mutate(
      { content: draft, rerun },
      {
        onSuccess: (summary) => {
          toast.success(
            `Text corrected${summary.fileCount > 1 ? ` on ${summary.fileCount} copies` : ""}`
          );
          setReview(null);
          onDone();
        },
      }
    );

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-3 py-2">
        <p className="text-xs text-muted-foreground">
          Correct what OCR misread. Marked names and search follow your edits.
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onDone}>
            Cancel
          </Button>
          <Button
            size="sm"
            className="h-7 text-xs"
            disabled={!isChanged || correct.isPending}
            onClick={openReview}
          >
            {correct.isPending && !review && <Loader2 className="h-3 w-3 animate-spin" />}
            Review changes
          </Button>
        </div>
      </div>
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        spellCheck={false}
        autoComplete="off"
        aria-label="Extracted text"
        className="min-h-0 flex-1 resize-none bg-transparent p-4 font-mono text-xs leading-relaxed text-foreground outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/50"
      />
      <Dialog open={review != null} onOpenChange={(open) => !open && setReview(null)}>
        <DialogContent className="border-border bg-card sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-sm">Save corrected text?</DialogTitle>
            <DialogDescription className="text-xs">
              {review && reviewIntro(review)}
            </DialogDescription>
          </DialogHeader>
          {review && <CorrectionReview summary={review} />}
          {review && review.rerunnable.length > 0 && (
            <fieldset className="space-y-1.5 text-xs">
              <legend className="mb-1.5 font-medium text-foreground">
                Run again on the corrected text (optional)
              </legend>
              {review.rerunnable.map((step) => (
                <label key={step} className="flex items-center gap-2 text-muted-foreground">
                  <Checkbox
                    checked={rerun.includes(step)}
                    onCheckedChange={(checked) =>
                      setRerun((steps) =>
                        checked ? [...steps, step] : steps.filter((s) => s !== step)
                      )
                    }
                  />
                  {humanize(step)}
                  {step === "textEmbedding" ? " (now)" : " (next pipeline run)"}
                </label>
              ))}
            </fieldset>
          )}
          {isRunning && review && (
            <Alert variant="destructive">
              <AlertDescription className="text-xs">
                Can’t save while {review.running.map(humanize).join(", ")} is running on this
                file. Try again when it finishes.
              </AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setReview(null)}>
              Keep editing
            </Button>
            <Button size="sm" disabled={correct.isPending || isRunning} onClick={save}>
              {correct.isPending && <Loader2 className="h-3 w-3 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function reviewIntro(summary: TextCorrectionSummary) {
  const copies =
    summary.fileCount > 1
      ? `This content appears as ${summary.fileCount} files; all of them get the corrected text. `
      : "";
  return `${copies}${summary.keptCount} marked name${summary.keptCount === 1 ? "" : "s"} on unchanged text keep their place.`;
}

/** Same mention on every copy collapses to one row. */
function grouped(mentions: CorrectedMention[]) {
  const rows = new Map<string, CorrectedMention & { count: number }>();
  for (const m of mentions) {
    const key = `${m.label}|${m.surfaceText}|${m.newSurfaceText ?? ""}`;
    const row = rows.get(key);
    if (row) row.count += 1;
    else rows.set(key, { ...m, count: 1 });
  }
  return [...rows.values()];
}

function CorrectionReview({ summary }: { summary: TextCorrectionSummary }) {
  const renamed = grouped(summary.renamed);
  const lost = grouped(summary.lost);
  return (
    <div className="space-y-3 text-xs">
      {renamed.length > 0 && (
        <section className="space-y-1.5">
          <h3 className="font-medium text-foreground">Marked names take the new spelling</h3>
          <ul className="space-y-1">
            {renamed.map((m) => (
              <li key={m.mentionId} className="flex items-center gap-2">
                <span className="text-muted-foreground">{humanize(m.label)}</span>
                <span className="font-mono">{m.surfaceText}</span>
                <ArrowRight size={12} className="text-muted-foreground" />
                <span className="font-mono text-foreground">{m.newSurfaceText}</span>
                {m.count > 1 && <span className="text-muted-foreground">×{m.count}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {lost.length > 0 && (
        <Alert variant="destructive">
          <AlertDescription className="space-y-1.5 text-xs">
            <p>These marked names are no longer in the text and will be removed:</p>
            <ul className="space-y-1">
              {lost.map((m) => (
                <li key={m.mentionId}>
                  <span className="text-muted-foreground">{humanize(m.label)}</span>{" "}
                  <span className="font-mono">{m.surfaceText}</span>
                  {m.count > 1 && <span className="text-muted-foreground"> ×{m.count}</span>}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
