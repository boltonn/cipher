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
import { cn } from "@/lib/utils";
import { Check, ChevronsUpDown, Database, X } from "lucide-react";
import { useState } from "react";

interface DatasetMultiSelectComboboxProps {
  value: string[];
  onChange: (datasetIds: string[]) => void;
  placeholder?: string;
  className?: string;
}

/** Multi-select dataset filter: type-ahead search backed by the real /datasets endpoint. */
export function DatasetMultiSelectCombobox({
  value,
  onChange,
  placeholder = "Filter by dataset...",
  className,
}: DatasetMultiSelectComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const { data, isFetching } = useDatasets({ query: query || undefined, limit: 20 });
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
            className="w-full justify-between bg-slate-900/40 border-white/10 hover:bg-slate-900/60 text-xs h-9"
          >
            <span className="flex items-center gap-2 truncate text-slate-400">
              <Database size={14} className="text-slate-500 shrink-0" />
              {value.length > 0 ? `${value.length} selected` : placeholder}
            </span>
            <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 text-slate-600" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0 bg-[#161920] border-white/10">
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Search datasets..."
              value={query}
              onValueChange={setQuery}
              className="text-xs"
            />
            <CommandList>
              {!isFetching && datasets.length === 0 && (
                <CommandEmpty className="text-xs text-slate-500 py-4">No datasets found</CommandEmpty>
              )}
              <CommandGroup>
                {datasets.map((dataset) => (
                  <CommandItem
                    key={dataset.id}
                    value={dataset.id}
                    onSelect={() => toggle(dataset.id)}
                    className="text-xs gap-2"
                  >
                    <Check
                      className={cn(
                        "h-3 w-3 shrink-0",
                        value.includes(dataset.id) ? "opacity-100" : "opacity-0"
                      )}
                    />
                    <span className="truncate flex-1">{dataset.name}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {value.length > 0 && (
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
    <Badge className="h-6 bg-indigo-500/10 text-indigo-300 border-none text-[11px] font-medium gap-1 pr-1.5">
      {dataset?.name || "Unnamed"}
      <button
        type="button"
        onClick={onRemove}
        className="hover:text-white ml-0.5"
        aria-label={`Remove ${dataset?.name || "dataset"}`}
      >
        <X size={11} />
      </button>
    </Badge>
  );
}
