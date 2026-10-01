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
import { Textarea } from "@/components/ui/textarea";
import { useUpdateDataset } from "@/features/datasets/api";
import { Dataset, DatasetUpdateSchema } from "@/features/datasets/types";
import { Loader2 } from "lucide-react";
import { useState } from "react";

const FIELD_LABEL = "text-[11px] uppercase tracking-wide text-muted-foreground";

interface EditDatasetDialogProps {
  dataset: Dataset;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditDatasetDialog({ dataset, isOpen, onOpenChange }: EditDatasetDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card border-border sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-white tracking-wide uppercase text-xs font-semibold">
            Edit Dataset
          </DialogTitle>
        </DialogHeader>
        {/* keyed by isOpen so each time the dialog opens it remounts with fresh state from `dataset` */}
        <EditDatasetForm key={String(isOpen)} dataset={dataset} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

type DatasetFieldErrors = { name?: string[]; description?: string[] };

function EditDatasetForm({ dataset, onDone }: { dataset: Dataset; onDone: () => void }) {
  const [name, setName] = useState(dataset.name);
  const [description, setDescription] = useState(dataset.description ?? "");
  const [fieldErrors, setFieldErrors] = useState<DatasetFieldErrors>({});

  const updateDataset = useUpdateDataset(dataset.id, onDone);

  const handleSubmit = () => {
    const result = DatasetUpdateSchema.safeParse({
      name: name.trim(),
      description: description.trim() || undefined,
    });
    if (!result.success) {
      setFieldErrors(result.error.flatten().fieldErrors as DatasetFieldErrors);
      return;
    }
    setFieldErrors({});
    updateDataset.mutate(result.data);
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

        {updateDataset.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {(updateDataset.error as Error).message || "Failed to update dataset"}
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
          disabled={updateDataset.isPending}
          className="bg-primary hover:bg-primary gap-2"
        >
          {updateDataset.isPending && <Loader2 size={14} className="animate-spin" />}
          Save Changes
        </Button>
      </DialogFooter>
    </>
  );
}
