"use client";

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
import { useTagNames } from "@/features/tags/hooks/use-tag-names";
import { Ban, Check, Loader2, Save, Tag, X } from "lucide-react";
import { useState } from "react";
import type { ImageAnnotation } from "../hooks/use-image-annotation";
import type { ImagePublic } from "../types";

interface ImageAnnotateBarProps {
  annotation: ImageAnnotation;
  /** Every image in the grid right now, for "label the rest". */
  loadedImages: ImagePublic[];
  onExit: () => void;
}

type PendingDialog = { kind: "clear"; authors: string[] } | { kind: "exit" };

/**
 * Bulk annotation toolbar: pick a tag, click cards to mark them positive / negative (or
 * label every unmarked card at once), then save all changes in one call.
 */
export function ImageAnnotateBar({
  annotation,
  loadedImages,
  onExit,
}: ImageAnnotateBarProps) {
  const { tag, counts, hasChanges, isSaving } = annotation;
  const [draft, setDraft] = useState(tag);
  const [prevTag, setPrevTag] = useState(tag);
  if (tag !== prevTag) {
    setPrevTag(tag);
    setDraft(tag);
  }
  const [dialog, setDialog] = useState<PendingDialog | null>(null);
  const { data: names = [] } = useTagNames("content");
  const suggestions = names.filter((name) =>
    name.toLowerCase().includes(draft.trim().toLowerCase())
  );
  const restCount = annotation.rest(loadedImages).length;

  const save = async () => {
    const authors = await annotation.clearConflicts();
    if (authors.length) setDialog({ kind: "clear", authors });
    else annotation.save();
  };

  return (
    <div className="sticky bottom-4 z-20 mx-auto flex w-fit max-w-full flex-col gap-1.5 rounded-2xl border border-border bg-popover px-3 py-2 shadow-lg">
      <div className="flex flex-wrap items-center gap-2">
        <Tag size={14} className="text-primary shrink-0" />
        <Autocomplete className="w-48">
          <AutocompleteInput
            value={draft}
            onValueChange={setDraft}
            onEnter={(value) => annotation.setTag(value)}
            onBlur={() => draft.trim() !== tag && annotation.setTag(draft)}
            placeholder="Tag to label…"
            disabled={hasChanges}
            className="h-8"
          />
          {suggestions.length > 0 && (
            <AutocompleteContent>
              {suggestions.map((name) => (
                <AutocompleteItem
                  key={name}
                  value={name}
                  onSelect={() => annotation.setTag(name)}
                >
                  {name}
                </AutocompleteItem>
              ))}
            </AutocompleteContent>
          )}
        </Autocomplete>

        <span className="flex items-center gap-2 text-[11px] font-bold tabular-nums">
          <span className="flex items-center gap-0.5 text-primary">
            <Check size={12} strokeWidth={3} />
            {counts.positive}
          </span>
          <span className="flex items-center gap-0.5 text-destructive">
            <Ban size={12} strokeWidth={3} />
            {counts.negative}
          </span>
          {counts.cleared > 0 && (
            <span className="text-muted-foreground">
              −{counts.cleared} cleared
            </span>
          )}
        </span>

        <Button
          size="sm"
          variant="outline"
          className="h-7 gap-1 text-[11px]"
          disabled={!tag || restCount === 0}
          onClick={() => annotation.labelRest(loadedImages, "positive")}
        >
          <Check size={12} /> Rest are “{tag || "…"}”
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-7 gap-1 text-[11px]"
          disabled={!tag || restCount === 0}
          onClick={() => annotation.labelRest(loadedImages, "negative")}
        >
          <Ban size={12} /> Rest are not
        </Button>

        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-[11px] text-muted-foreground"
          disabled={!hasChanges || isSaving}
          onClick={annotation.reset}
        >
          Reset
        </Button>
        <Button
          size="sm"
          className="h-7 gap-1 text-[11px]"
          disabled={!hasChanges || isSaving}
          onClick={save}
        >
          {isSaving ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Save size={12} />
          )}
          Save
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="size-7 text-muted-foreground"
          aria-label="Stop annotating"
          onClick={() => (hasChanges ? setDialog({ kind: "exit" }) : onExit())}
        >
          <X size={14} />
        </Button>
      </div>
      <p className="px-1 text-[11px] text-muted-foreground">
        {tag
          ? `Click a card: tagged → not → unlabelled · shift-click copies a label across a range${hasChanges ? " · save or reset to switch tags" : ""}`
          : "Pick a tag, then click cards to label them"}
      </p>

      <AlertDialog
        open={dialog !== null}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <AlertDialogContent>
          {dialog?.kind === "clear" ? (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle>Clear “{tag}” for everyone?</AlertDialogTitle>
                <AlertDialogDescription>
                  {dialog.authors.join(", ")} also labelled some of the{" "}
                  {counts.cleared} images you set back to unlabelled. Saving
                  removes their labels too.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Go back</AlertDialogCancel>
                <AlertDialogAction onClick={annotation.save}>
                  Save anyway
                </AlertDialogAction>
              </AlertDialogFooter>
            </>
          ) : (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle>Discard unsaved labels?</AlertDialogTitle>
                <AlertDialogDescription>
                  {counts.positive + counts.negative + counts.cleared} label
                  changes for “{tag}” haven’t been saved.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep annotating</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => {
                    annotation.reset();
                    onExit();
                  }}
                >
                  Discard
                </AlertDialogAction>
              </AlertDialogFooter>
            </>
          )}
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
