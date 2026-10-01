"use client";

import { Button } from "@/components/ui/button";
import {
  useRejectFaces,
  useUnrejectFaces,
} from "@/features/faces/hooks/use-reject-faces";
import type { FaceSelection } from "@/features/faces/hooks/use-face-selection";
import { Ban, Loader2, RotateCcw, UserMinus } from "lucide-react";

interface FaceSelectionBarProps {
  selection: FaceSelection;
  /** Ids of every face currently loaded, for "Select all". */
  loadedIds: string[];
  /** Viewing rejected faces: offer Restore instead of Not a face. */
  isRejectedView?: boolean;
  /** Person page: detach faces from the person without calling them not-a-face. */
  onUnassign?: (faceIds: string[]) => void;
  isUnassigning?: boolean;
}

/** Floating bulk-action bar for a face grid; renders nothing until a face is selected. */
export function FaceSelectionBar({
  selection,
  loadedIds,
  isRejectedView,
  onUnassign,
  isUnassigning,
}: FaceSelectionBarProps) {
  const reject = useRejectFaces(selection.clear);
  const unreject = useUnrejectFaces(selection.clear);
  const count = selection.selectedIds.size;
  if (count === 0) return null;

  const ids = [...selection.selectedIds];
  const isBusy = reject.isPending || unreject.isPending || !!isUnassigning;

  return (
    <div className="sticky bottom-4 z-20 mx-auto flex w-fit items-center gap-2 rounded-full border border-border bg-popover px-3 py-1.5 shadow-lg">
      <span className="text-[11px] text-muted-foreground tabular-nums">
        {count.toLocaleString()} selected
      </span>
      {count < loadedIds.length && (
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-[11px] text-muted-foreground"
          onClick={() => selection.selectAll(loadedIds)}
        >
          Select all {loadedIds.length.toLocaleString()}
        </Button>
      )}
      {isRejectedView ? (
        <Button
          size="sm"
          className="h-7 gap-1 text-[11px]"
          disabled={isBusy}
          onClick={() => unreject.mutate(ids)}
        >
          {unreject.isPending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <RotateCcw size={12} />
          )}
          Restore
        </Button>
      ) : (
        <>
          {onUnassign && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-[11px]"
              disabled={isBusy}
              onClick={() => onUnassign(ids)}
            >
              {isUnassigning ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <UserMinus size={12} />
              )}
              Unassign
            </Button>
          )}
          <Button
            size="sm"
            variant="destructive"
            className="h-7 gap-1 text-[11px]"
            disabled={isBusy}
            onClick={() => reject.mutate(ids)}
          >
            {reject.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Ban size={12} />
            )}
            Not a face
          </Button>
        </>
      )}
      <Button
        size="sm"
        variant="ghost"
        className="h-7 px-2 text-[11px] text-muted-foreground"
        onClick={selection.clear}
      >
        Clear
      </Button>
    </div>
  );
}
