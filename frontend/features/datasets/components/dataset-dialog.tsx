"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateDataset } from "@/features/datasets/api";
import { useCreateDataset } from "@/features/datasets/hooks/use-create-dataset";
import { Dataset, DatasetCreate, DatasetCreateSchema, DatasetUpdateSchema } from "@/features/datasets/types";
import { Loader2 } from "lucide-react";
import { useState } from "react";

const FIELD_LABEL = "text-[11px] uppercase tracking-wide text-muted-foreground";

interface DatasetDialogProps {
  /** The dataset to edit; omit to create a new one. */
  dataset?: Dataset;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Create (admin) or edit a dataset's name, description and discoverability. */
export function DatasetDialog({ dataset, isOpen, onOpenChange }: DatasetDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card border-border sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-white tracking-wide uppercase text-xs font-semibold">
            {dataset ? "Edit dataset" : "New dataset"}
          </DialogTitle>
        </DialogHeader>
        {/* keyed by isOpen so each time the dialog opens it remounts with fresh state from `dataset` */}
        <DatasetForm key={String(isOpen)} dataset={dataset} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

type DatasetFieldErrors = { name?: string[]; description?: string[] };

function DatasetForm({ dataset, onDone }: { dataset?: Dataset; onDone: () => void }) {
  const [name, setName] = useState(dataset?.name ?? "");
  const [description, setDescription] = useState(dataset?.description ?? "");
  const [isDiscoverable, setIsDiscoverable] = useState(dataset?.isDiscoverable ?? false);
  const [fieldErrors, setFieldErrors] = useState<DatasetFieldErrors>({});

  const updateDataset = useUpdateDataset(dataset?.id ?? "", onDone);
  const createDataset = useCreateDataset(onDone);
  const saveDataset = dataset ? updateDataset : createDataset;

  const handleSubmit = () => {
    const result = (dataset ? DatasetUpdateSchema : DatasetCreateSchema).safeParse({
      name: name.trim(),
      description: description.trim() || undefined,
      isDiscoverable,
    });
    if (!result.success) {
      setFieldErrors(result.error.flatten().fieldErrors as DatasetFieldErrors);
      return;
    }
    setFieldErrors({});
    if (dataset) updateDataset.mutate(result.data);
    else createDataset.mutate(result.data as DatasetCreate);
  };

  return (
    <>
      <div className="space-y-4">
        <Field data-invalid={!!fieldErrors.name}>
          <FieldLabel htmlFor="edit-dataset-name" className={FIELD_LABEL}>
            Name
          </FieldLabel>
          <Input
            id="edit-dataset-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={!!fieldErrors.name}
            placeholder="e.g. Q2 Communications Dump"
            className="bg-muted/40 border-border text-sm"
          />
          <FieldError errors={fieldErrors.name?.map((message) => ({ message }))} />
        </Field>

        <Field data-invalid={!!fieldErrors.description}>
          <FieldLabel htmlFor="edit-dataset-description" className={FIELD_LABEL}>
            Description
          </FieldLabel>
          <Textarea
            id="edit-dataset-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            aria-invalid={!!fieldErrors.description}
            placeholder="What is this dataset and where does it come from?"
            className="bg-muted/40 border-border text-sm min-h-24"
          />
          <FieldError errors={fieldErrors.description?.map((message) => ({ message }))} />
        </Field>

        <Field orientation="horizontal" className="items-center justify-between">
          <div>
            <FieldLabel htmlFor="edit-dataset-discoverable" className={FIELD_LABEL}>
              Discoverable
            </FieldLabel>
            <p className="text-xs text-muted-foreground">
              Non-members see it listed with a lock, but can&apos;t open, triage or search it.
            </p>
          </div>
          <Switch
            id="edit-dataset-discoverable"
            checked={isDiscoverable}
            onCheckedChange={setIsDiscoverable}
          />
        </Field>

        {saveDataset.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {(saveDataset.error as Error).message || "Failed to save dataset"}
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
          disabled={saveDataset.isPending}
          className="bg-primary hover:bg-primary gap-2"
        >
          {saveDataset.isPending && <Loader2 size={14} className="animate-spin" />}
          {dataset ? "Save changes" : "Create dataset"}
        </Button>
      </DialogFooter>
    </>
  );
}
