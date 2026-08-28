"use client";

import { Button } from "@/components/ui/button";
import { facesService } from "@/features/faces/api";
import { getFaceCropStyle } from "@/features/faces/components/face-crop";
import { usePendingFaceMatches, useResolveFaceMatch } from "@/features/faces/hooks/use-face-matches";
import { FaceMatch } from "@/features/faces/types";
import { usePerson, usePersonRepresentativeFaces } from "@/features/persons/hooks/use-persons";
import { BadgeCheck, Check, Sparkles, UserRound, X } from "lucide-react";

interface PotentialMatchesProps {
  faceId: string;
}

/**
 * Candidate persons proposed for this face by the background KNN matching
 * job, awaiting analyst review. Distinct from an actual assignment: nothing
 * here has been applied to the face yet -- confirming one does.
 */
export function PotentialMatches({ faceId }: PotentialMatchesProps) {
  const { data, isPending } = usePendingFaceMatches(faceId);
  const matches = data?.data ?? [];

  if (isPending || matches.length === 0) return null;

  return (
    <section className="p-4 rounded-xl bg-black/40 border border-annotation/20 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles size={14} className="text-annotation" />
        <h4 className="text-[10px] font-black text-foreground uppercase tracking-widest">
          Potential Matches
        </h4>
        <span className="text-[9px] font-mono text-muted-foreground">awaiting review</span>
      </div>
      <div className="flex flex-col gap-2">
        {matches.map((match) => (
          <PotentialMatchRow key={match.id} match={match} />
        ))}
      </div>
    </section>
  );
}

function PotentialMatchRow({ match }: { match: FaceMatch }) {
  const { data: person } = usePerson(match.personId);
  const { data: faces } = usePersonRepresentativeFaces(match.personId);
  const primaryFace = faces?.[0];
  const resolve = useResolveFaceMatch();

  const cropStyle = primaryFace
    ? getFaceCropStyle(primaryFace.boundingBox, facesService.getFaceViewUrl(primaryFace.id))
    : undefined;

  return (
    <div className="flex items-center gap-3 p-2 rounded-lg bg-muted/40 border border-border/50">
      <div
        className="h-10 w-10 rounded-full shrink-0 overflow-hidden bg-primary/10 bg-cover bg-center text-primary text-xs font-black flex items-center justify-center"
        style={cropStyle}
      >
        {!primaryFace && (person?.name ? person.name[0].toUpperCase() : <UserRound size={16} />)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1">
          <p className="text-xs font-bold text-foreground truncate">{person?.name || "Unnamed"}</p>
          {person?.isVerified && <BadgeCheck size={11} className="text-primary shrink-0" />}
        </div>
        <p className="text-[10px] font-mono text-annotation">
          {(match.similarityScore * 100).toFixed(0)}% similar
        </p>
      </div>
      <div className="flex items-center gap-1">
        <Button
          size="icon"
          variant="ghost"
          onClick={() => resolve.mutate({ id: match.id, status: "confirmed" })}
          disabled={resolve.isPending}
          title="Confirm match"
          className="h-7 w-7 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300"
        >
          <Check size={14} />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          onClick={() => resolve.mutate({ id: match.id, status: "rejected" })}
          disabled={resolve.isPending}
          title="Reject match"
          className="h-7 w-7 bg-destructive/10 text-destructive hover:bg-destructive/20 hover:text-destructive"
        >
          <X size={14} />
        </Button>
      </div>
    </div>
  );
}
