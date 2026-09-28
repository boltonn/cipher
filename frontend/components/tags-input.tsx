"use client";

import {
  Autocomplete,
  AutocompleteContent,
  AutocompleteInput,
  AutocompleteItem,
} from "@/components/ui/autocomplete";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";
import { useState } from "react";

interface TagsInputProps {
  value: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  className?: string;
  /**
   * Existing tags to offer below the input, most-relevant first. Pair with
   * `onQueryChange` (typically backed by a debounced query) for a live
   * search-as-you-type dropdown; omit both for a plain chip input.
   */
  suggestions?: string[];
  onQueryChange?: (query: string) => void;
  isLoadingSuggestions?: boolean;
}

/**
 * Chip-based tag input: type + Enter/comma to add a tag, click the x or hit
 * Backspace on an empty input to remove the last one. With `suggestions` +
 * `onQueryChange` wired up it doubles as a type-ahead over existing tags, so
 * an analyst reuses "pycon" instead of minting "PyCon" / "py-con" duplicates.
 */
export function TagsInput({
  value,
  onChange,
  placeholder = "Add a tag…",
  className,
  suggestions,
  onQueryChange,
  isLoadingSuggestions,
}: TagsInputProps) {
  const [draft, setDraft] = useState("");
  const suggesting = !!onQueryChange;

  const add = (raw: string) => {
    const tag = raw.trim();
    if (tag && !value.includes(tag)) onChange([...value, tag]);
    setDraft("");
    onQueryChange?.("");
  };

  const removeTag = (tag: string) => onChange(value.filter((t) => t !== tag));

  const options = (suggestions ?? []).filter((s) => !value.includes(s));

  return (
    <div className={cn("space-y-1.5", className)}>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((tag) => (
            <Badge
              key={tag}
              className="h-6 animate-in gap-1 rounded-full border-none bg-primary/10 px-2.5 pr-1.5 text-xs font-medium text-primary fade-in zoom-in-95"
            >
              {tag}
              <button
                type="button"
                onClick={() => removeTag(tag)}
                className="rounded-full p-0.5 text-primary/60 hover:bg-primary/20 hover:text-primary"
                aria-label={`Remove ${tag}`}
              >
                <X size={11} />
              </button>
            </Badge>
          ))}
        </div>
      )}
      <Autocomplete>
        <AutocompleteInput
          value={draft}
          onValueChange={(v) => {
            setDraft(v);
            onQueryChange?.(v);
          }}
          onEnter={add}
          placeholder={placeholder}
          className="h-9"
          onKeyDown={(e) => {
            if (e.key === ",") {
              e.preventDefault();
              add(draft);
            } else if (e.key === "Backspace" && !draft && value.length > 0) {
              removeTag(value[value.length - 1]);
            }
          }}
        />
        {suggesting && (
          <AutocompleteContent isLoading={isLoadingSuggestions} emptyMessage="No matching tags">
            {options.map((tag) => (
              <AutocompleteItem key={tag} value={tag} onSelect={() => add(tag)}>
                {tag}
              </AutocompleteItem>
            ))}
          </AutocompleteContent>
        )}
      </Autocomplete>
    </div>
  );
}
