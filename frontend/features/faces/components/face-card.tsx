"use client";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { facesService } from "@/features/faces/api";
import { FacePublic, FaceSimilarityResult } from "@/features/faces/types";
import { cn } from "@/lib/utils";
import { BadgeCheck, Maximize2, ScanFace, Search, Sparkles, UserCheck, UserPlus } from "lucide-react";
import Image from "next/image";
import { memo } from "react";

interface FaceCardProps {
  face: FacePublic | FaceSimilarityResult;
  onFindSimilar?: (id: string) => void;
  onExpand?: (face: FacePublic) => void;
  onCreatePerson?: (face: FacePublic) => void;
}

const FaceCardImpl: React.FC<FaceCardProps> = ({ face, onFindSimilar, onExpand, onCreatePerson }) => {
  const similarityScore = "similarityScore" in face ? face.similarityScore : undefined;

  const isCandidateOnly = face.status === "matched" && !face.personId && !!face.candidatePersonName;
  // Name is denormalized onto FacePublic (personName / candidatePersonName), so
  // a grid of cards never fetches a person per card.
  const displayName = face.personId ? face.personName : face.candidatePersonName;

  return (
    <div className="group relative rounded-xl overflow-hidden bg-muted/40 border border-border/50 transition-colors duration-200 hover:border-primary/40 hover:bg-muted/60">
      <div
        role="button"
        tabIndex={0}
        className="aspect-square relative w-full bg-background cursor-pointer"
        onClick={() => onExpand?.(face)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onExpand?.(face);
          }
        }}
      >
        {/* Small server-cropped thumbnail (~10 KB) -- not the full source photo.
            next/image is lazy by default, so offscreen virtualized rows don't
            fetch/decode. */}
        <Image
          src={facesService.getFaceThumbnailUrl(face.id)}
          alt=""
          fill
          unoptimized
          sizes="(max-width: 640px) 50vw, (max-width: 1280px) 20vw, 16vw"
          className="object-cover"
        />

        <div className="absolute inset-x-0 bottom-3 flex justify-center opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-300 z-10">
          <div
            className="flex items-center gap-4 bg-popover/95 border border-border px-4 py-2 rounded-full shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <NavAction
              icon={<Search size={16} />}
              label="Find Similar"
              onClick={() => onFindSimilar?.(face.id)}
            />
            <NavAction
              icon={<Maximize2 size={16} />}
              label="Expand"
              onClick={() => onExpand?.(face)}
            />
            <NavAction
              icon={<UserPlus size={16} />}
              label="Create Person"
              onClick={() => onCreatePerson?.(face)}
            />
          </div>
        </div>

        {similarityScore != null && (
          <span className="absolute top-2 left-2 text-[9px] font-mono font-bold text-annotation bg-background/85 border border-annotation/30 px-1.5 py-0.5 rounded">
            {(similarityScore * 100).toFixed(0)}% match
          </span>
        )}
      </div>

      <div className="p-2.5 border-t border-border/50 space-y-1">
        {face.status === "verified" ? (
          <Badge className="text-[9px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 w-full justify-start bg-primary/10 text-primary">
            <BadgeCheck size={10} className="shrink-0" />
            Verified
          </Badge>
        ) : face.status === "matched" ? (
          <Badge
            className={cn(
              "text-[9px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 w-full justify-start",
              isCandidateOnly ? "bg-annotation/10 text-annotation" : "bg-primary/10 text-primary"
            )}
          >
            {isCandidateOnly ? <Sparkles size={10} className="shrink-0" /> : <UserCheck size={10} className="shrink-0" />}
            Matched
          </Badge>
        ) : (
          <Badge className="text-[9px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 bg-white/5 text-muted-foreground w-full justify-start">
            <ScanFace size={10} className="shrink-0" />
            Unmatched
          </Badge>
        )}
        {/* Always rendered (nbsp when empty) so every card is the same height and
            the virtualized grid doesn't have to re-measure rows on scroll. */}
        <p
          className={cn(
            "text-[10px] truncate px-0.5",
            isCandidateOnly ? "text-annotation/80 italic" : "text-muted-foreground"
          )}
        >
          {displayName ? (isCandidateOnly ? `(${displayName})` : displayName) : " "}
        </p>
      </div>
    </div>
  );
};

/**
 * Memoized: the grid re-renders this on every scroll tick and after any
 * `["persons"]`/`["faces"]` cache change. With stable callbacks from the
 * container, `memo` lets untouched cards skip re-rendering entirely.
 */
export const FaceCard = memo(FaceCardImpl);

const NavAction = ({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}) => (
  <Tooltip delayDuration={0}>
    <TooltipTrigger asChild>
      <button
        type="button"
        onClick={onClick}
        className="cursor-pointer text-muted-foreground hover:text-annotation transition-all duration-200 hover:drop-shadow-[0_0_8px_rgba(245,158,11,0.8)] outline-none"
      >
        {icon}
      </button>
    </TooltipTrigger>
    <TooltipContent
      sideOffset={12}
      className="bg-popover border-border text-[9px] font-bold uppercase tracking-widest text-annotation px-2 py-1 rounded-md shadow-2xl border [&_svg]:hidden!"
    >
      {label}
    </TooltipContent>
  </Tooltip>
);
