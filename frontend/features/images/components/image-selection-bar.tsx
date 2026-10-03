"use client";

import { SelectionBar } from "@/components/selection-bar";
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
import {
  Autocomplete,
  AutocompleteContent,
  AutocompleteInput,
  AutocompleteItem,
} from "@/components/ui/autocomplete";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useTagImages } from "@/features/images/api";
import type { ModelTagType } from "@/features/images/types";
import { tagService } from "@/features/tags/api";
import type { TagFilterState } from "@/features/tags/types";
import type { GridSelection } from "@/hooks/use-grid-selection";
import { Check, Loader2, Tag, X } from "lucide-react";
import { useState } from "react";

interface ImageSelectionBarProps {
  selection: GridSelection;
  /** Ids of every image currently loaded, for "Select all". */
  loadedIds: string[];
  /** The tag the grid is filtered to, if exactly one: offers one-click accept / reject for it. */
  reviewTag?: string;
  reviewTagState?: TagFilterState;
  /** Tags already in use on the loaded images, suggested so the same tag is reused. */
  knownTags: string[];
}

/** Bulk actions for an image grid: add or remove a tag, and accept / reject the filtered tag. */
export function ImageSelectionBar({
  selection,
  loadedIds,
  reviewTag,
  reviewTagState = "positive",
  knownTags,
}: ImageSelectionBarProps) {
  const [isTagOpen, setIsTagOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const tagImages = useTagImages(() => {
    selection.clear();
    setIsTagOpen(false);
    setDraft("");
  });

  const [pendingClear, setPendingClear] = useState<{
    tag: string;
    authors: string[];
  } | null>(null);

  const imageIds = [...selection.selectedIds];
  const label = (tag: string, type?: ModelTagType) => {
    if (tag.trim()) tagImages.mutate({ imageIds, tag: tag.trim(), type });
  };
  // Clearing removes the tag for everyone -- ask first if other people labelled any of these.
  const clear = async (tag: string) => {
    const authors = await tagService.labelAuthors({
      targetType: "content",
      targetIds: imageIds,
      tag: tag.trim(),
    });
    if (authors.length > 0) setPendingClear({ tag: tag.trim(), authors });
    else label(tag);
  };
  const suggestions = knownTags.filter((tag) =>
    tag.toLowerCase().includes(draft.trim().toLowerCase())
  );

  return (
    <SelectionBar selection={selection} loadedIds={loadedIds}>
      <Popover open={isTagOpen} onOpenChange={setIsTagOpen}>
        <PopoverTrigger asChild>
          <Button
            size="sm"
            variant={reviewTag ? "outline" : "default"}
            className="h-7 gap-1 text-[11px]"
            disabled={tagImages.isPending}
          >
            {tagImages.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Tag size={12} />
            )}
            Tag
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-64 space-y-2 border-border bg-popover p-3">
          <Autocomplete>
            <AutocompleteInput
              value={draft}
              onValueChange={setDraft}
              onEnter={(tag) => label(tag, "positive")}
              placeholder="Tag name…"
              className="h-9"
            />
            {suggestions.length > 0 && (
              <AutocompleteContent>
                {suggestions.map((tag) => (
                  <AutocompleteItem
                    key={tag}
                    value={tag}
                    onSelect={() => setDraft(tag)}
                  >
                    {tag}
                  </AutocompleteItem>
                ))}
              </AutocompleteContent>
            )}
          </Autocomplete>
          <div className="flex gap-2">
            <Button
              size="sm"
              className="h-7 flex-1 text-[11px]"
              disabled={!draft.trim() || tagImages.isPending}
              onClick={() => label(draft, "positive")}
            >
              Add tag
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 flex-1 text-[11px]"
              disabled={!draft.trim() || tagImages.isPending}
              onClick={() => clear(draft)}
            >
              Remove tag
            </Button>
          </div>
        </PopoverContent>
      </Popover>
      {reviewTag && reviewTagState !== "positive" && (
        <Button
          size="sm"
          className="h-7 gap-1 text-[11px]"
          disabled={tagImages.isPending}
          onClick={() => label(reviewTag, "positive")}
        >
          <Check size={12} />
          Accept “{reviewTag}”
        </Button>
      )}
      {reviewTag && reviewTagState !== "negative" && (
        <Button
          size="sm"
          variant="destructive"
          className="h-7 gap-1 text-[11px]"
          disabled={tagImages.isPending}
          onClick={() => label(reviewTag, "negative")}
        >
          <X size={12} />
          Reject “{reviewTag}”
        </Button>
      )}
      <AlertDialog
        open={pendingClear !== null}
        onOpenChange={(open) => !open && setPendingClear(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove “{pendingClear?.tag}”?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingClear?.authors.join(", ")} also labelled some of these
              images. Removing it takes it off for everyone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingClear) label(pendingClear.tag);
                setPendingClear(null);
              }}
            >
              Remove for everyone
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SelectionBar>
  );
}
