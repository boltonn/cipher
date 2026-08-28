"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateDataset } from "@/features/datasets/api";
import { Dataset, DatasetUpdateSchema } from "@/features/datasets/types";
import { Loader2 } from "lucide-react";
import { useState } from "react";

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
          <DialogTitle className="text-white tracking-[0.1em] uppercase text-xs font-black">
            Edit Dataset
          </DialogTitle>
        </DialogHeader>
        {/* keyed by isOpen so each time the dialog opens it remounts with fresh state from `dataset` */}
        <EditDatasetForm key={String(isOpen)} dataset={dataset} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function EditDatasetForm({ dataset, onDone }: { dataset: Dataset; onDone: () => void }) {
  const [name, setName] = useState(dataset.name);
  const [description, setDescription] = useState(dataset.description ?? "");
  const [validationError, setValidationError] = useState<string | null>(null);

  const updateDataset = useUpdateDataset(dataset.id, onDone);

  const handleSubmit = () => {
    const result = DatasetUpdateSchema.safeParse({
      name: name.trim(),
      description: description.trim() || undefined,
    });
    if (!result.success) {
      setValidationError(result.error.issues[0].message);
      return;
    }
    setValidationError(null);
    updateDataset.mutate(result.data);
  };

  const displayError =
    validationError ?? (updateDataset.isError ? (updateDataset.error as Error).message : null);

  return (
    <>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="edit-dataset-name" className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Name
          </Label>
          <Input
            id="edit-dataset-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Q2 Communications Dump"
            className="bg-muted/40 border-border text-sm"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="edit-dataset-description" className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Description
          </Label>
          <Textarea
            id="edit-dataset-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this dataset and where does it come from?"
            className="bg-muted/40 border-border text-sm min-h-24"
          />
        </div>

        {displayError && (
          <p className="text-[11px] text-destructive">{displayError}</p>
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
