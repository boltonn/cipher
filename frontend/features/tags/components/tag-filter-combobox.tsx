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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { Ban, Check, ChevronsUpDown, Sparkles, Tag, X } from "lucide-react";
import { useState } from "react";
import { useTagNames } from "../hooks/use-tag-names";
import {
  nextTagFilterState,
  tagFilterEntries,
  tagFilterState,
  withTagFilterState,
} from "../tag-filter";
import type { TagFilterState, TagFilterValue, TagTargetType } from "../types";

export const TAG_FILTER_STYLES: Record<
  TagFilterState,
  { label: string; icon: typeof Check; className: string }
> = {
  positive: {
    label: "Tagged",
    icon: Check,
    className: "bg-primary/15 text-primary border-primary/30",
  },
  negative: {
    label: "Not",
    icon: Ban,
    className: "bg-destructive/15 text-destructive border-destructive/30",
  },
  predicted: {
    label: "Predicted",
    icon: Sparkles,
    className: "bg-annotation/15 text-annotation border-annotation/30",
  },
};

interface TagFilterComboboxProps {
  value: TagFilterValue;
  onChange: (value: TagFilterValue) => void;
  targetType?: TagTargetType;
  /** Offer the "predicted" (unlabelled model prediction) state in the click cycle. */
  allowPredicted?: boolean;
  className?: string;
}

/**
 * Multi-select tag filter where each click cycles a tag's state: tagged -> not tagged ->
 * (predicted) -> off. Chips below cycle the same way; the x drops a tag.
 */
export function TagFilterCombobox({
  value,
  onChange,
  targetType = "content",
  allowPredicted = false,
  className,
}: TagFilterComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const { data: names = [] } = useTagNames(targetType);
  const entries = tagFilterEntries(value);
  const draft = query.trim();
  const options = [
    ...new Set([...entries.map((entry) => entry.tag), ...names]),
  ];

  const cycle = (tag: string) =>
    onChange(
      withTagFilterState(
        value,
        tag,
        nextTagFilterState(tagFilterState(value, tag), allowPredicted)
      )
    );

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="h-9 w-full justify-between border-border bg-muted/40 text-xs hover:bg-muted/60"
          >
            <span className="flex items-center gap-2 truncate text-muted-foreground">
              <Tag size={14} className="shrink-0" />
              {entries.length > 0
                ? `${entries.length} tag filter${entries.length === 1 ? "" : "s"}`
                : "Filter by tag..."}
            </span>
            <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 text-muted-foreground" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 border-border bg-popover p-0">
          <Command>
            <CommandInput
              placeholder="Search tags..."
              value={query}
              onValueChange={setQuery}
              className="text-xs"
            />
            <p className="border-b border-border px-3 py-1.5 text-[11px] text-muted-foreground">
              Click to cycle: tagged → not
              {allowPredicted ? " → predicted" : ""} → off
            </p>
            <CommandList>
              <CommandEmpty className="py-4 text-center text-xs text-muted-foreground">
                No tags found
              </CommandEmpty>
              <CommandGroup>
                {draft && !options.includes(draft) && (
                  <CommandItem
                    value={draft}
                    onSelect={() => cycle(draft)}
                    className="gap-2 text-xs"
                  >
                    <Tag className="h-3 w-3 shrink-0 opacity-60" />
                    Filter “{draft}”
                  </CommandItem>
                )}
                {options.map((tag) => (
                  <TagFilterOption
                    key={tag}
                    tag={tag}
                    state={tagFilterState(value, tag)}
                    onSelect={() => cycle(tag)}
                  />
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {entries.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {entries.map(({ tag, state }) => (
            <TagFilterChip
              key={tag}
              tag={tag}
              state={state}
              onCycle={() => cycle(tag)}
              onRemove={() =>
                onChange(withTagFilterState(value, tag, undefined))
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function TagFilterOption({
  tag,
  state,
  onSelect,
}: {
  tag: string;
  state: TagFilterState | undefined;
  onSelect: () => void;
}) {
  const style = state && TAG_FILTER_STYLES[state];
  const Icon = style?.icon ?? Check;
  return (
    <CommandItem value={tag} onSelect={onSelect} className="gap-2 text-xs">
      <span
        className={cn(
          "flex size-4 shrink-0 items-center justify-center rounded border",
          style ? style.className : "border-border text-transparent"
        )}
      >
        <Icon className="size-3" />
      </span>
      <span className="flex-1 truncate">{tag}</span>
      {style && (
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {style.label}
        </span>
      )}
    </CommandItem>
  );
}

function TagFilterChip({
  tag,
  state,
  onCycle,
  onRemove,
}: {
  tag: string;
  state: TagFilterState;
  onCycle: () => void;
  onRemove: () => void;
}) {
  const style = TAG_FILTER_STYLES[state];
  const Icon = style.icon;
  return (
    <Badge
      className={cn(
        "h-6 gap-1 border pr-1 text-[11px] font-medium",
        style.className
      )}
    >
      <button
        type="button"
        onClick={onCycle}
        className="flex items-center gap-1"
        title="Click to change how this tag filters"
      >
        <Icon size={11} />
        {state === "negative" ? `not ${tag}` : tag}
      </button>
      <button
        type="button"
        onClick={onRemove}
        className="ml-0.5 opacity-70 hover:opacity-100"
        aria-label={`Remove ${tag} filter`}
      >
        <X size={11} />
      </button>
    </Badge>
  );
}
