"use client";

import { DatasetMultiSelectCombobox } from "@/features/datasets/components/dataset-multi-select-combobox";
import { cn } from "@/lib/utils";

interface DatasetSelectProps {
  datasetIds: string[];
  onChange: (datasetIds: string[]) => void;
  /** Trigger text when nothing is selected. */
  placeholder?: string;
  className?: string;
}

/** The page-header dataset picker: several datasets at once, names on the trigger. */
export function DatasetSelect({ datasetIds, onChange, placeholder = "Select datasets", className }: DatasetSelectProps) {
  return (
    <DatasetMultiSelectCombobox
      compact
      value={datasetIds}
      onChange={onChange}
      placeholder={placeholder}
      className="w-52"
      triggerClassName={cn("h-8", className)}
    />
  );
}
