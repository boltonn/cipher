"use client";

import { SelectionBar } from "@/components/selection-bar";
import { Button } from "@/components/ui/button";
import type { FacePublic } from "@/features/faces/types";
import { CreatePersonDialog } from "@/features/persons/components/create-person-dialog";
import { useAssignFaces } from "@/features/faces/hooks/use-assign-face";
import {
  useRejectFaces,
  useUnrejectFaces,
} from "@/features/faces/hooks/use-reject-faces";
import type { GridSelection } from "@/hooks/use-grid-selection";
import { PersonPicker } from "@/features/persons/components/person-picker";
import {
  Ban,
  Loader2,
  RotateCcw,
  UserCheck,
  UserMinus,
  UserPlus,
} from "lucide-react";
import { useState } from "react";

interface FaceSelectionBarProps {
  selection: GridSelection;
  /** Ids of every face currently loaded, for "Select all". */
  loadedIds: string[];
  /** Loaded faces in result order: enables "Create person" from the first selected one. */
  faces?: FacePublic[];
  selectAllCount?: number;
  onSelectAll?: () => void;
  isSelectingAll?: boolean;
  /** Viewing rejected faces: offer Restore instead of Not a face. */
  isRejectedView?: boolean;
  /** Person page: detach faces from the person without calling them not-a-face. */
  onUnassign?: (faceIds: string[]) => void;
  isUnassigning?: boolean;
}

/** Bulk actions for a face grid: create person, assign, unassign, not a face / restore. */
export function FaceSelectionBar({
  selection,
  loadedIds,
  faces,
  selectAllCount,
  onSelectAll,
  isSelectingAll,
  isRejectedView,
  onUnassign,
  isUnassigning,
}: FaceSelectionBarProps) {
  const reject = useRejectFaces(selection.clear);
  const unreject = useUnrejectFaces(selection.clear);
  const assign = useAssignFaces(selection.clear);
  const ids = [...selection.selectedIds];
  const [isCreatingPerson, setIsCreatingPerson] = useState(false);
  const referenceFace = faces?.find((face) =>
    selection.selectedIds.has(face.id)
  );
  const isBusy =
    reject.isPending ||
    unreject.isPending ||
    assign.isPending ||
    !!isUnassigning;

  return (
    <SelectionBar
      selection={selection}
      loadedIds={loadedIds}
      selectAllCount={selectAllCount}
      onSelectAll={onSelectAll}
      isSelectingAll={isSelectingAll}
    >
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
          {referenceFace && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-[11px]"
              disabled={isBusy}
              onClick={() => setIsCreatingPerson(true)}
            >
              <UserPlus size={12} />
              Create person
            </Button>
          )}
          <PersonPicker
            withAvatars
            onSelect={(personId, personName) =>
              assign.mutate({ faceIds: ids, personId, personName })
            }
          >
            <Button
              size="sm"
              className="h-7 gap-1 text-[11px]"
              disabled={isBusy}
            >
              {assign.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <UserCheck size={12} />
              )}
              Assign to person
            </Button>
          </PersonPicker>
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
          <CreatePersonDialog
            isOpen={isCreatingPerson}
            onOpenChange={setIsCreatingPerson}
            sourceFace={referenceFace}
            extraFaceIds={ids.filter((id) => id !== referenceFace?.id)}
            onCreated={selection.clear}
          />
        </>
      )}
    </SelectionBar>
  );
}
