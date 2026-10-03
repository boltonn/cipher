"use client";

import { useAnnotateImages } from "@/features/images/api";
import type { ImagePublic, ModelTagType } from "@/features/images/types";
import { tagService } from "@/features/tags/api";
import { useCallback, useMemo, useRef, useState } from "react";

/** An image's label for one tag; `null` is unlabelled. */
export type AnnotationLabel = ModelTagType | null;

interface StagedLabel {
  label: AnnotationLabel;
  /** What the image had when it was first staged, so a change back is no change. */
  original: AnnotationLabel;
}

const labelOf = (image: ImagePublic, tag: string): AnnotationLabel =>
  image.tags.includes(tag)
    ? "positive"
    : image.negativeTags.includes(tag)
      ? "negative"
      : null;

/** Click order on a card: unlabelled -> positive -> negative -> unlabelled. */
const NEXT: Record<string, AnnotationLabel> = {
  null: "positive",
  positive: "negative",
  negative: null,
};

export interface ImageAnnotation {
  tag: string;
  setTag: (tag: string) => void;
  /** The label the card shows: staged if touched, else its saved one. */
  labelFor: (image: ImagePublic) => AnnotationLabel;
  isStaged: (imageId: string) => boolean;
  /** Advance one image's label; `range` (shift-click) gives everything since the last click the same label. */
  cycle: (image: ImagePublic, ordered: ImagePublic[], range: boolean) => void;
  /** The images not yet clicked that have no saved label for this tag. */
  rest: (images: ImagePublic[]) => ImagePublic[];
  /** Give every one of `rest(images)` `label`. */
  labelRest: (images: ImagePublic[], label: ModelTagType) => void;
  reset: () => void;
  counts: { positive: number; negative: number; cleared: number };
  hasChanges: boolean;
  /** Names of other users whose labels the pending clears would remove -- confirm before `save`. */
  clearConflicts: () => Promise<string[]>;
  save: () => void;
  isSaving: boolean;
}

/**
 * Staged, bulk labelling of one tag over an image grid: click cards to mark them positive /
 * negative, then save every change in one call. Staged labels survive new searches, so a
 * pass can span several queries ("car", then "red car") before saving.
 */
export function useImageAnnotation(initialTag = ""): ImageAnnotation {
  const [tag, setTagState] = useState(initialTag);
  const [staged, setStaged] = useState<Map<string, StagedLabel>>(
    () => new Map()
  );
  const anchorRef = useRef<string | null>(null);
  const annotate = useAnnotateImages(() => setStaged(new Map()));

  const setTag = useCallback((next: string) => {
    setTagState(next.trim());
    setStaged(new Map());
    anchorRef.current = null;
  }, []);

  const labelFor = useCallback(
    (image: ImagePublic) => {
      const entry = staged.get(image.id);
      return entry ? entry.label : labelOf(image, tag);
    },
    [staged, tag]
  );

  const stage = useCallback(
    (images: ImagePublic[], label: (image: ImagePublic) => AnnotationLabel) =>
      setStaged((prev) => {
        const next = new Map(prev);
        for (const image of images) {
          const original = prev.get(image.id)?.original ?? labelOf(image, tag);
          next.set(image.id, { label: label(image), original });
        }
        return next;
      }),
    [tag]
  );

  const cycle = useCallback(
    (image: ImagePublic, ordered: ImagePublic[], range: boolean) => {
      const anchorIndex = ordered.findIndex((i) => i.id === anchorRef.current);
      const index = ordered.findIndex((i) => i.id === image.id);
      const isRange = range && anchorIndex >= 0 && index >= 0;
      // A range copies the last-clicked card's label instead of cycling each card on its own.
      const label = isRange
        ? labelFor(ordered[anchorIndex])
        : NEXT[String(labelFor(image))];
      const targets = isRange
        ? ordered.slice(
            Math.min(anchorIndex, index),
            Math.max(anchorIndex, index) + 1
          )
        : [image];
      stage(targets, () => label);
      anchorRef.current = image.id;
    },
    [labelFor, stage]
  );

  const rest = useCallback(
    (images: ImagePublic[]) =>
      images.filter(
        (image) => !staged.has(image.id) && labelOf(image, tag) === null
      ),
    [staged, tag]
  );

  const labelRest = useCallback(
    (images: ImagePublic[], label: ModelTagType) =>
      stage(rest(images), () => label),
    [rest, stage]
  );

  const changes = useMemo(() => {
    const byLabel = {
      positive: [] as string[],
      negative: [] as string[],
      cleared: [] as string[],
    };
    for (const [id, { label, original }] of staged) {
      if (label === original) continue;
      byLabel[label ?? "cleared"].push(id);
    }
    return byLabel;
  }, [staged]);

  const counts = {
    positive: changes.positive.length,
    negative: changes.negative.length,
    cleared: changes.cleared.length,
  };

  return {
    tag,
    setTag,
    labelFor,
    isStaged: (imageId) => {
      const entry = staged.get(imageId);
      return !!entry && entry.label !== entry.original;
    },
    cycle,
    rest,
    labelRest,
    reset: () => {
      setStaged(new Map());
      anchorRef.current = null;
    },
    counts,
    hasChanges: counts.positive + counts.negative + counts.cleared > 0,
    clearConflicts: () =>
      changes.cleared.length
        ? tagService.labelAuthors({
            targetType: "content",
            targetIds: changes.cleared,
            tag,
          })
        : Promise.resolve([]),
    save: () => annotate.mutate({ tag, ...changes }),
    isSaving: annotate.isPending,
  };
}
