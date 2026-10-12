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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { TagsInput } from "@/components/tags-input";
import { useRunPlanActions } from "@/features/runs/hooks/use-run-plans";
import { STAGING } from "@/features/runs/types";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { z } from "zod";

const FIELD_LABEL = "text-[11px] uppercase tracking-wide text-muted-foreground";

interface StagingSource {
  uri: string;
  include: string[];
  exclude: string[];
}

const stagingSourceSchema = z.object({
  uri: z
    .string()
    .trim()
    .min(1, "Where are the files?")
    .regex(/^(s3:\/\/[^/]+|\/|~|file:\/\/)/, "A directory (/data/dump) or s3://bucket/prefix/"),
  include: z.array(z.string()),
  exclude: z.array(z.string()),
});

/** Where to stage from: a directory or s3://bucket/prefix, plus path globs. */
function StagingFields({
  source,
  onChange,
  error,
}: {
  source: StagingSource;
  onChange: (source: StagingSource) => void;
  error?: string;
}) {
  return (
    <div className="space-y-4">
      <Field data-invalid={!!error}>
        <FieldLabel htmlFor="staging-uri" className={FIELD_LABEL}>
          Stage files from
        </FieldLabel>
        <Input
          id="staging-uri"
          value={source.uri}
          onChange={(event) => onChange({ ...source, uri: event.target.value })}
          aria-invalid={!!error}
          placeholder="s3://bucket/prefix/ or /data/dump"
          autoComplete="off"
          className="bg-muted/40 border-border font-mono text-sm"
        />
        <FieldDescription className="text-xs">
          Read only. Files stay where they are; each row points at its file.
        </FieldDescription>
        <FieldError errors={error ? [{ message: error }] : undefined} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field>
          <FieldLabel className={FIELD_LABEL}>Only paths matching</FieldLabel>
          <TagsInput
            value={source.include}
            onChange={(include) => onChange({ ...source, include })}
            placeholder="*.pdf, mail/*"
          />
        </Field>
        <Field>
          <FieldLabel className={FIELD_LABEL}>Skip paths matching</FieldLabel>
          <TagsInput
            value={source.exclude}
            onChange={(exclude) => onChange({ ...source, exclude })}
            placeholder="*.tmp, Thumbs.db"
          />
        </Field>
      </div>
    </div>
  );
}

interface StageFilesDialogProps {
  datasetId: string;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Admin: stage files into a dataset from a directory or s3://bucket/prefix (more files later re-uses it). */
export function StageFilesDialog({ datasetId, isOpen, onOpenChange }: StageFilesDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card border-border sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-white tracking-wide uppercase text-xs font-semibold">Stage files</DialogTitle>
          <DialogDescription className="text-xs">
            Queued for a worker straight away. Files already staged are skipped.
          </DialogDescription>
        </DialogHeader>
        <StageFilesForm key={String(isOpen)} datasetId={datasetId} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function StageFilesForm({ datasetId, onDone }: { datasetId: string; onDone: () => void }) {
  const [source, setSource] = useState<StagingSource>({ uri: "", include: [], exclude: [] });
  const [error, setError] = useState<string>();
  const { create } = useRunPlanActions();

  const submit = () => {
    const parsed = stagingSourceSchema.safeParse(source);
    if (!parsed.success) {
      setError(parsed.error.issues[0].message);
      return;
    }
    setError(undefined);
    create.mutate({ datasetId, steps: [{ stepType: STAGING, parameters: parsed.data }] }, { onSuccess: onDone });
  };

  return (
    <>
      <StagingFields source={source} onChange={setSource} error={error} />
      <DialogFooter>
        <Button variant="ghost" onClick={onDone} className="text-muted-foreground">
          Cancel
        </Button>
        <Button onClick={submit} disabled={create.isPending}>
          {create.isPending && <Loader2 className="animate-spin" />}
          Stage files
        </Button>
      </DialogFooter>
    </>
  );
}
