"use client";

import { GradientButton } from "@/components/ui/gradient-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCreateDataset } from "@/features/datasets/hooks/use-create-dataset";
import { DatasetCreateSchema } from "@/features/datasets/types";
import { useState } from "react";

interface DatasetRequestFormProps {
  onSuccess?: () => void;
}

export function DatasetRequestForm({ onSuccess }: DatasetRequestFormProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const {
    mutate,
    isPending,
    error: mutationError,
  } = useCreateDataset(onSuccess);

  const handleSubmit = () => {
    const result = DatasetCreateSchema.safeParse({
      name,
      description: description || undefined,
    });
    if (!result.success) {
      setValidationError(result.error.issues[0].message);
      return;
    }
    setValidationError(null);
    mutate(result.data);
  };

  const displayError =
    validationError ??
    (mutationError ? (mutationError as Error).message : null);

  return (
    <div className="shadow-input mx-auto rounded-none bg-card p-4 md:rounded-2xl md:p-8">
      <h2 className="text-xl font-bold text-slate-100">Request a Dataset</h2>
      <p className="mt-2 max-w-sm text-sm text-slate-500">
        Submit a dataset to be ingested and processed by Cipher.
      </p>

      <form className="my-8" action={handleSubmit}>
        <div className="mb-4 flex flex-col space-y-2">
          <Label htmlFor="ds-name">Dataset Name</Label>
          <Input
            id="ds-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Q2 Communications Dump"
          />
        </div>

        <div className="mb-8 flex flex-col space-y-2">
          <Label htmlFor="ds-description">Description</Label>
          <Textarea
            id="ds-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this dataset and where does it come from?"
            rows={4}
          />
        </div>

        {displayError && (
          <p className="mb-4 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {displayError}
          </p>
        )}

        <GradientButton
          type="submit"
          isLoading={isPending}
          loadingText="Submitting…"
        >
          Submit Request →
        </GradientButton>
      </form>
    </div>
  );
}
