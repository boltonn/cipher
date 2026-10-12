"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PersonAvatar } from "@/features/persons/components/person-avatar";
import { useMergePerson } from "@/features/persons/hooks/use-persons";
import type { Person } from "@/features/persons/types";
import { cn } from "@/lib/utils";
import { BadgeCheck, Loader2, Merge } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

interface MergePersonsDialogProps {
  persons: Person[];
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onMerged?: () => void;
}

/** Fold several selected people into one kept record; the others are deleted. */
export function MergePersonsDialog({
  persons,
  isOpen,
  onOpenChange,
  onMerged,
}: MergePersonsDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card border-border sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-foreground">
            Merge {persons.length} people
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Choose the record to keep. Faces, matches, events, comments, mentions
            and connections from the others move onto it, and the others are
            deleted.
          </DialogDescription>
        </DialogHeader>
        <MergePersonsForm
          key={String(isOpen)}
          persons={persons}
          onDone={() => {
            onOpenChange(false);
            onMerged?.();
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

function MergePersonsForm({
  persons,
  onDone,
}: {
  persons: Person[];
  onDone: () => void;
}) {
  const [keptId, setKeptId] = useState(
    () => (persons.find((p) => p.isVerified) ?? persons[0])?.id
  );
  const [mergedIds, setMergedIds] = useState<string[]>([]);
  const [isMerging, setIsMerging] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const merge = useMergePerson();

  const kept = persons.find((p) => p.id === keptId);
  const removed = persons.filter((p) => p.id !== keptId && !mergedIds.includes(p.id));
  const visible = persons.filter((p) => !mergedIds.includes(p.id));

  const runMerge = async () => {
    if (!kept) return;
    setIsMerging(true);
    setError(undefined);
    let facesMoved = 0;
    try {
      for (const source of removed) {
        const result = await merge.mutateAsync({ targetId: kept.id, sourceId: source.id });
        facesMoved += result.facesMoved;
        setMergedIds((prev) => [...prev, source.id]);
      }
      toast.success(
        `Merged ${removed.length} into ${kept.name || "person"} — ${facesMoved} face${
          facesMoved === 1 ? "" : "s"
        } moved`
      );
      onDone();
    } catch {
      setError("A merge failed partway. People already merged stay merged; try again for the rest.");
      setIsMerging(false);
    }
  };

  return (
    <>
      <div className="flex max-h-80 flex-col gap-1.5 overflow-y-auto">
        {visible.map((p) => {
          const isKept = p.id === keptId;
          return (
            <button
              key={p.id}
              type="button"
              disabled={isMerging || mergedIds.length > 0}
              onClick={() => setKeptId(p.id)}
              className={cn(
                "flex items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors",
                isKept
                  ? "border-primary/40 bg-primary/5"
                  : "border-border bg-muted/40 hover:bg-muted/60"
              )}
            >
              <PersonAvatar person={p} size="md" />
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1 truncate text-sm font-medium text-foreground">
                  {p.name || "Unnamed"}
                  {p.isVerified && <BadgeCheck size={13} className="shrink-0 text-primary" />}
                </p>
                {p.aliases.length > 0 && (
                  <p className="truncate text-[11px] text-muted-foreground">
                    a.k.a. {p.aliases.join(", ")}
                  </p>
                )}
              </div>
              <span
                className={cn(
                  "shrink-0 text-[11px] font-medium",
                  isKept ? "text-primary" : "text-destructive/80"
                )}
              >
                {isKept ? "Keep" : "Merge in"}
              </span>
            </button>
          );
        })}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <DialogFooter>
        <Button
          onClick={runMerge}
          disabled={!kept || removed.length === 0 || isMerging}
          className="gap-1.5"
        >
          {isMerging ? <Loader2 size={14} className="animate-spin" /> : <Merge size={14} />}
          {isMerging
            ? `Merging into ${kept?.name || "kept person"}…`
            : `Merge into ${kept?.name || "kept person"}`}
        </Button>
      </DialogFooter>
    </>
  );
}
