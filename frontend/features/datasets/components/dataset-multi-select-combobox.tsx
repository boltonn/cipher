"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useDataset, useDatasets } from "@/features/datasets/api";
import { DatasetLock } from "@/features/datasets/components/dataset-lock";
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import { Check, ChevronsUpDown, Database, X } from "lucide-react";
import { useState } from "react";

interface DatasetMultiSelectComboboxProps {
  value: string[];
  onChange: (datasetIds: string[]) => void;
  placeholder?: string;
  className?: string;
  /** Trigger only, no chips of the selection below it (for tight toolbars). */
  compact?: boolean;
  triggerClassName?: string;
}

/** Multi-select dataset filter: type-ahead search backed by the real /datasets endpoint. */
export function DatasetMultiSelectCombobox({
  value,
  onChange,
  placeholder = "Filter by dataset...",
  className,
  compact = false,
  triggerClassName,
}: DatasetMultiSelectComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 250);

  const { data, isFetching } = useDatasets({ query: debouncedQuery || undefined, limit: 20 });
  const datasets = data?.pages.flatMap((page) => page.data) ?? [];

  const toggle = (datasetId: string) => {
    const next = new Set(value);
    if (next.has(datasetId)) next.delete(datasetId);
    else next.add(datasetId);
    onChange(Array.from(next));
  };

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className={cn(
              "w-full justify-between bg-muted/40 border-border hover:bg-muted/60 text-xs h-9",
              triggerClassName
            )}
          >
            <span className="flex items-center gap-2 truncate text-muted-foreground">
              <Database size={14} className="text-muted-foreground shrink-0" />
              {value.length > 0 ? `${value.length} selected` : placeholder}
            </span>
            <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 text-muted-foreground" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0 bg-popover border-border">
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Search datasets..."
              value={query}
              onValueChange={setQuery}
              className="text-xs"
            />
            <CommandList>
              {!isFetching && datasets.length === 0 && (
                <CommandEmpty className="text-xs text-muted-foreground py-4">No datasets found</CommandEmpty>
              )}
              <CommandGroup>
                {datasets.map((dataset) => (
                  <CommandItem
                    key={dataset.id}
                    value={dataset.id}
                    onSelect={() => toggle(dataset.id)}
                    disabled={!dataset.hasAccess}
                  className="text-xs gap-2"
                  >
                    <Check
                      className={cn(
                        "h-3 w-3 shrink-0",
                        value.includes(dataset.id) ? "opacity-100" : "opacity-0"
                      )}
                    />
                    <span className="truncate flex-1">{dataset.name}</span>
                  {!dataset.hasAccess && <DatasetLock />}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {!compact && value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((datasetId) => (
            <SelectedDatasetChip key={datasetId} datasetId={datasetId} onRemove={() => toggle(datasetId)} />
          ))}
        </div>
      )}
    </div>
  );
}

function SelectedDatasetChip({ datasetId, onRemove }: { datasetId: string; onRemove: () => void }) {
  const { data: dataset } = useDataset(datasetId);

  return (
    <Badge className="h-6 bg-primary/10 text-primary border-none text-[11px] font-medium gap-1 pr-1.5">
      {dataset?.name || "Unnamed"}
      <button
        type="button"
        onClick={onRemove}
        className="hover:text-foreground ml-0.5"
        aria-label={`Remove ${dataset?.name || "dataset"}`}
      >
        <X size={11} />
      </button>
    </Badge>
  );
}
