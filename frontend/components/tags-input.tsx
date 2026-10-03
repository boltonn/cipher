"use client";

import {
  Autocomplete,
  AutocompleteContent,
  AutocompleteInput,
  AutocompleteItem,
} from "@/components/ui/autocomplete";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
  /** Who/what set a tag, shown on hover; `isModel` paints the chip in the AI/ML annotation color. */
  describeTag?: (tag: string) => { label: string; isModel?: boolean } | undefined;
  /** A message when removing `tag` needs confirming (e.g. another user added it); undefined removes at once. */
  confirmRemove?: (tag: string) => string | undefined;
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
  describeTag,
  confirmRemove,
}: TagsInputProps) {
  const [draft, setDraft] = useState("");
  const [pendingRemoval, setPendingRemoval] = useState<{
    tag: string;
    message: string;
  } | null>(null);
  const suggesting = !!onQueryChange;

  const add = (raw: string) => {
    const tag = raw.trim();
    if (tag && !value.includes(tag)) onChange([...value, tag]);
    setDraft("");
    onQueryChange?.("");
  };

  const removeNow = (tag: string) => onChange(value.filter((t) => t !== tag));
  const removeTag = (tag: string) => {
    const message = confirmRemove?.(tag);
    if (message) setPendingRemoval({ tag, message });
    else removeNow(tag);
  };

  const options = (suggestions ?? []).filter((s) => !value.includes(s));

  return (
    <div className={cn("space-y-1.5", className)}>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((tag) => {
            const about = describeTag?.(tag);
            const chip = (
              <Badge
                key={tag}
                className={cn(
                  "h-6 animate-in gap-1 rounded-full border-none px-2.5 pr-1.5 text-xs font-medium fade-in zoom-in-95",
                  about?.isModel
                    ? "bg-annotation/15 text-annotation"
                    : "bg-primary/10 text-primary"
                )}
              >
                {tag}
                <button
                  type="button"
                  onClick={() => removeTag(tag)}
                  className="rounded-full p-0.5 opacity-60 hover:bg-current/10 hover:opacity-100"
                  aria-label={`Remove ${tag}`}
                >
                  <X size={11} />
                </button>
              </Badge>
            );
            return about ? (
              <Tooltip key={tag}>
                <TooltipTrigger asChild>{chip}</TooltipTrigger>
                <TooltipContent>{about.label}</TooltipContent>
              </Tooltip>
            ) : (
              chip
            );
          })}
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
      <AlertDialog
        open={pendingRemoval !== null}
        onOpenChange={(open) => !open && setPendingRemoval(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove “{pendingRemoval?.tag}”?</AlertDialogTitle>
            <AlertDialogDescription>{pendingRemoval?.message}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingRemoval) removeNow(pendingRemoval.tag);
                setPendingRemoval(null);
              }}
            >
              Remove for everyone
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
