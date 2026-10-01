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
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { facesService } from "@/features/faces/api";
import { PersonAvatar } from "@/features/persons/components/person-avatar";
import { PersonPicker } from "@/features/persons/components/person-picker";
import {
  useMergePerson,
  usePerson,
  usePersonMergeCandidates,
  usePersonRepresentativeFaces,
} from "@/features/persons/hooks/use-persons";
import { Person, PersonMergeSuggestion } from "@/features/persons/types";
import { cn } from "@/lib/utils";
import { AlertTriangle, ArrowRight, Loader2, Sparkles, UserRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

interface MergePersonDialogProps {
  /** The surviving record -- everything folds onto this person. */
  person: Person;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MergePersonDialog({ person, isOpen, onOpenChange }: MergePersonDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card border-border sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-white tracking-wide uppercase text-xs font-semibold">
            Merge Person
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Fold a duplicate record into{" "}
            <span className="text-foreground font-medium">{person.name || "this person"}</span>. The
            other record is deleted.
          </DialogDescription>
        </DialogHeader>
        <MergePersonForm key={String(isOpen)} person={person} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

/** A horizontal strip of a person's representative face thumbnails. */
function FaceStrip({ personId }: { personId: string }) {
  const { data: faces } = usePersonRepresentativeFaces(personId);
  const shown = (faces ?? []).slice(0, 5);
  if (shown.length === 0) return null;
  return (
    <div className="flex flex-wrap justify-center gap-1">
      {shown.map((face) => (
        // eslint-disable-next-line @next/next/no-img-element -- tiny same-origin crop, server-downscaled
        <img
          key={face.id}
          src={facesService.getFaceThumbnailUrl(face.id)}
          alt=""
          className="h-9 w-9 rounded border border-border object-cover"
        />
      ))}
    </div>
  );
}

function PersonPreview({
  person,
  tone,
}: {
  person: Pick<Person, "id" | "name"> & { aliases?: string[] };
  tone: "keep" | "remove";
}) {
  return (
    <div
      className={cn(
        "flex flex-1 flex-col items-center gap-2 rounded-xl border p-3 text-center",
        tone === "remove" ? "border-destructive/30 bg-destructive/5" : "border-primary/30 bg-primary/5"
      )}
    >
      <span
        className={cn(
          "text-[11px] font-bold uppercase tracking-wide",
          tone === "remove" ? "text-destructive" : "text-primary"
        )}
      >
        {tone === "remove" ? "Deleted" : "Kept"}
      </span>
      <PersonAvatar person={person} size="lg" />
      <div className="min-w-0 w-full">
        <p className="truncate text-sm font-semibold text-foreground">{person.name || "Unnamed"}</p>
        {person.aliases && person.aliases.length > 0 && (
          <p className="truncate text-[11px] text-muted-foreground">aka {person.aliases.join(", ")}</p>
        )}
      </div>
      <FaceStrip personId={person.id} />
    </div>
  );
}

/** One suggested-match row: click to pick it as the record to merge in. */
function SuggestionChip({
  suggestion,
  selected,
  onPick,
}: {
  suggestion: PersonMergeSuggestion;
  selected: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      className={cn(
        "flex shrink-0 items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-xs transition-colors",
        selected
          ? "border-primary bg-primary/10 text-foreground"
          : "border-border bg-muted/40 text-muted-foreground hover:border-primary/40 hover:text-foreground"
      )}
    >
      <PersonAvatar person={suggestion} size="sm" className="shrink-0" />
      <span className="max-w-32 truncate font-medium">{suggestion.name || "Unnamed"}</span>
      <span className="font-mono text-[11px] text-annotation">
        {Math.round(suggestion.similarityScore * 100)}%
      </span>
    </button>
  );
}

function MergePersonForm({ person, onDone }: { person: Person; onDone: () => void }) {
  const [sourceId, setSourceId] = useState<string | undefined>();
  const [idInput, setIdInput] = useState("");
  const { data: source, isError: sourceNotFound } = usePerson(sourceId);
  const { data: candidates = [] } = usePersonMergeCandidates(person.id);

  const merge = useMergePerson(person.id, onDone);

  // Prefer the already-loaded suggestion row so the preview fills in instantly.
  const sourcePreview = source ?? candidates.find((c) => c.id === sourceId);

  const samePerson = sourceId === person.id;
  const canMerge = !!sourceId && !samePerson && !sourceNotFound;

  const runMerge = () => {
    if (!sourceId) return;
    merge.mutate(sourceId, {
      onSuccess: (result) => {
        // the picked person is gone now -- stop the previews / usePerson from
        // pointing at a deleted id before the dialog finishes closing
        setSourceId(undefined);
        toast.success(
          `Merged into ${person.name || "person"} — ${result.facesMoved} face${
            result.facesMoved === 1 ? "" : "s"
          }, ${result.relationshipsMoved} connection${
            result.relationshipsMoved === 1 ? "" : "s"
          } moved`
        );
      },
    });
  };

  return (
    <>
      <div className="space-y-4">
        {candidates.length > 0 && (
          <div className="space-y-1.5">
            <Label className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
              <Sparkles size={12} className="text-annotation" />
              Likely the same person
            </Label>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {candidates.map((candidate) => (
                <SuggestionChip
                  key={candidate.id}
                  suggestion={candidate}
                  selected={sourceId === candidate.id}
                  onPick={() => setSourceId(candidate.id)}
                />
              ))}
            </div>
          </div>
        )}

        <div className="space-y-1.5">
          <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Person to merge in
          </Label>
          <PersonPicker
            value={sourceId}
            valueName={sourcePreview?.name}
            placeholder="Select the duplicate…"
            withAvatars
            allowCreate={false}
            onSelect={(id) => setSourceId(id)}
          />
          <div className="flex items-center gap-2">
            <Input
              value={idInput}
              onChange={(e) => setIdInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && idInput.trim()) setSourceId(idInput.trim());
              }}
              placeholder="…or paste a person ID"
              className="h-8 bg-muted/40 border-border text-xs font-mono"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!idInput.trim()}
              onClick={() => setSourceId(idInput.trim())}
              className="h-8 shrink-0 text-xs"
            >
              Use ID
            </Button>
          </div>
        </div>

        {samePerson && (
          <Alert variant="destructive">
            <AlertDescription>Pick a different person than this one.</AlertDescription>
          </Alert>
        )}

        {sourceId && !samePerson && sourceNotFound && (
          <Alert variant="destructive">
            <AlertDescription>No person with ID {sourceId}.</AlertDescription>
          </Alert>
        )}

        <div className="flex items-center gap-2">
          {canMerge ? (
            <PersonPreview
              person={{
                id: sourceId!,
                name: sourcePreview?.name,
                aliases: sourcePreview?.aliases,
              }}
              tone="remove"
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-border p-3 text-center text-[11px] text-muted-foreground min-h-[168px]">
              <UserRound size={20} className="text-muted-foreground/60" />
              Pick a person to merge in
            </div>
          )}
          <ArrowRight size={18} className="shrink-0 text-muted-foreground" />
          <PersonPreview person={person} tone="keep" />
        </div>

        <Alert className="border-annotation/30 bg-annotation/5">
          <AlertTriangle size={14} className="text-annotation" />
          <AlertDescription className="text-[11px] leading-relaxed text-muted-foreground">
            Faces, pending matches, event roles, comments, mentions and connections move onto{" "}
            <span className="text-foreground">{person.name || "this person"}</span>. Moved faces lose
            their exemplar (representative / primary) flags — re-pick them afterward. This cannot be
            undone.
          </AlertDescription>
        </Alert>

        {merge.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {(merge.error as Error)?.message || "Failed to merge person"}
            </AlertDescription>
          </Alert>
        )}
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onDone} className="text-muted-foreground">
          Cancel
        </Button>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              disabled={!canMerge || merge.isPending}
              variant="destructive"
              className="gap-2"
            >
              {merge.isPending && <Loader2 size={14} className="animate-spin" />}
              Merge…
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent className="bg-card border-border">
            <AlertDialogHeader>
              <AlertDialogTitle>
                Merge {sourcePreview?.name || "this person"} into {person.name || "this person"}?
              </AlertDialogTitle>
              <AlertDialogDescription>
                The{" "}
                <span className="font-medium text-foreground">
                  {sourcePreview?.name || "source"}
                </span>{" "}
                record is permanently deleted. Its faces, pending matches, event roles, comments,
                mentions and connections move onto {person.name || "the surviving person"}. This
                can&apos;t be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={runMerge}
                className="bg-destructive text-white hover:bg-destructive/90"
              >
                Merge &amp; delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogFooter>
    </>
  );
}
