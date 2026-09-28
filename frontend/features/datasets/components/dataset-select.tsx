"use client";

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
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import { Check, ChevronsUpDown, Database, X } from "lucide-react";
import { useState } from "react";

interface DatasetSelectProps {
  datasetId?: string;
  onChange: (datasetId: string | undefined) => void;
  className?: string;
}

/** Single-select dataset filter: type-ahead search backed by the real /datasets endpoint. */
export function DatasetSelect({ datasetId, onChange, className }: DatasetSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  // Type-ahead: the field updates instantly, the fetch waits for a pause.
  const debouncedQuery = useDebounce(query, 250);

  const { data, isFetching } = useDatasets({ query: debouncedQuery || undefined, limit: 20 });
  const datasets = data?.pages.flatMap((page) => page.data) ?? [];
  const { data: selected } = useDataset(datasetId);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "h-7 w-56 justify-between border-border bg-muted/40 text-xs hover:bg-muted/60",
            className
          )}
        >
          <span className={cn("flex items-center gap-2 truncate", datasetId ? "text-foreground" : "text-muted-foreground")}>
            <Database size={13} className="shrink-0 text-muted-foreground" />
            {datasetId ? (selected?.name ?? "...") : "All datasets"}
          </span>
          {datasetId ? (
            <span
              role="button"
              tabIndex={0}
              aria-label="Clear dataset filter"
              className="ml-2 shrink-0 text-muted-foreground hover:text-white"
              onClick={(e) => {
                e.stopPropagation();
                onChange(undefined);
              }}
            >
              <X size={12} />
            </span>
          ) : (
            <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 text-muted-foreground" />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 border-border bg-popover p-0">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search datasets..." value={query} onValueChange={setQuery} className="text-xs" />
          <CommandList>
            {!isFetching && datasets.length === 0 && (
              <CommandEmpty className="py-4 text-xs text-muted-foreground">No datasets found</CommandEmpty>
            )}
            <CommandGroup>
              {datasets.map((dataset) => (
                <CommandItem
                  key={dataset.id}
                  value={dataset.id}
                  onSelect={() => {
                    onChange(dataset.id === datasetId ? undefined : dataset.id);
                    setOpen(false);
                  }}
                  className="gap-2 text-xs"
                >
                  <Check className={cn("h-3 w-3 shrink-0", dataset.id === datasetId ? "opacity-100" : "opacity-0")} />
                  <span className="flex-1 truncate">{dataset.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
