"use client";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { facesService } from "@/features/faces/api";
import { FacePublic, FaceSimilarityResult } from "@/features/faces/types";
import { cn } from "@/lib/utils";
import {
  Ban,
  BadgeCheck,
  Check,
  Maximize2,
  RotateCcw,
  ScanFace,
  Search,
  Sparkles,
  UserCheck,
  UserPlus,
} from "lucide-react";
import Image from "next/image";
import { memo } from "react";

interface FaceCardProps {
  face: FacePublic | FaceSimilarityResult;
  onFindSimilar?: (id: string) => void;
  onExpand?: (face: FacePublic) => void;
  onCreatePerson?: (face: FacePublic) => void;
  /** Mark (or, for a rejected face, restore) this one face as not a face. */
  onReject?: (face: FacePublic) => void;
  onRestore?: (face: FacePublic) => void;
  isSelected?: boolean;
  /** Something in the grid is selected: a click toggles selection instead of expanding. */
  isSelectionActive?: boolean;
  onToggleSelect?: (face: FacePublic, range: boolean) => void;
}

const FaceCardImpl: React.FC<FaceCardProps> = ({
  face,
  onFindSimilar,
  onExpand,
  onCreatePerson,
  onReject,
  onRestore,
  isSelected,
  isSelectionActive,
  onToggleSelect,
}) => {
  const similarityScore =
    "similarityScore" in face ? face.similarityScore : undefined;
  const isRejected = face.status === "rejected";
  const isAutoRejected = isRejected && face.rejectionMethod === "automatic";

  const activate = (range: boolean) => {
    if (onToggleSelect && (isSelectionActive || range))
      onToggleSelect(face, range);
    else onExpand?.(face);
  };

  const isCandidateOnly =
    face.status === "matched" && !face.personId && !!face.candidatePersonName;
  // Name is denormalized onto FacePublic (personName / candidatePersonName), so
  // a grid of cards never fetches a person per card.
  const displayName = face.personId
    ? face.personName
    : face.candidatePersonName;

  return (
    <div
      className={cn(
        "group relative rounded-xl overflow-hidden bg-muted/40 border border-border/50 transition-colors duration-200 hover:border-primary/40 hover:bg-muted/60",
        isSelected && "border-primary ring-2 ring-primary/40"
      )}
    >
      <div
        role="button"
        tabIndex={0}
        aria-pressed={isSelectionActive ? !!isSelected : undefined}
        className="aspect-square relative w-full bg-background cursor-pointer"
        onClick={(e) => activate(e.shiftKey)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            activate(e.shiftKey);
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
          className={cn("object-cover", isRejected && "grayscale opacity-60")}
        />

        {onToggleSelect && (
          <button
            type="button"
            aria-label={isSelected ? "Deselect face" : "Select face"}
            onClick={(e) => {
              e.stopPropagation();
              onToggleSelect(face, e.shiftKey);
            }}
            className={cn(
              "absolute top-2 right-2 z-10 flex size-5 items-center justify-center rounded-md border transition-opacity",
              isSelected
                ? "bg-primary border-primary text-primary-foreground opacity-100"
                : "bg-background/80 border-border text-transparent opacity-0 group-hover:opacity-100",
              isSelectionActive && "opacity-100"
            )}
          >
            <Check size={12} strokeWidth={3} />
          </button>
        )}

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
            {!isRejected && (
              <NavAction
                icon={<UserPlus size={16} />}
                label="Create Person"
                onClick={() => onCreatePerson?.(face)}
              />
            )}
            {isRejected
              ? onRestore && (
                  <NavAction
                    icon={<RotateCcw size={16} />}
                    label="Restore"
                    onClick={() => onRestore(face)}
                  />
                )
              : onReject && (
                  <NavAction
                    icon={<Ban size={16} />}
                    label="Not a face"
                    onClick={() => onReject(face)}
                  />
                )}
          </div>
        </div>

        {similarityScore != null && (
          <span className="absolute top-2 left-2 text-[11px] font-mono font-bold text-annotation bg-background/85 border border-annotation/30 px-1.5 py-0.5 rounded">
            {(similarityScore * 100).toFixed(0)}% match
          </span>
        )}
      </div>

      <div className="p-2.5 border-t border-border/50 space-y-1">
        {isRejected ? (
          <Badge
            className={cn(
              "text-[11px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 w-full justify-start",
              isAutoRejected
                ? "bg-annotation/10 text-annotation"
                : "bg-destructive/10 text-destructive"
            )}
          >
            {isAutoRejected ? (
              <Sparkles size={10} className="shrink-0" />
            ) : (
              <Ban size={10} className="shrink-0" />
            )}
            {isAutoRejected ? "Auto-rejected" : "Not a face"}
          </Badge>
        ) : face.status === "verified" ? (
          <Badge className="text-[11px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 w-full justify-start bg-primary/10 text-primary">
            <BadgeCheck size={10} className="shrink-0" />
            Verified
          </Badge>
        ) : face.status === "matched" ? (
          <Badge
            className={cn(
              "text-[11px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 w-full justify-start",
              isCandidateOnly
                ? "bg-annotation/10 text-annotation"
                : "bg-primary/10 text-primary"
            )}
          >
            {isCandidateOnly ? (
              <Sparkles size={10} className="shrink-0" />
            ) : (
              <UserCheck size={10} className="shrink-0" />
            )}
            Matched
          </Badge>
        ) : (
          <Badge className="text-[11px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 bg-white/5 text-muted-foreground w-full justify-start">
            <ScanFace size={10} className="shrink-0" />
            Unmatched
          </Badge>
        )}
        {/* Always rendered (nbsp when empty) so every card is the same height and
            the virtualized grid doesn't have to re-measure rows on scroll. */}
        <p
          className={cn(
            "text-[11px] truncate px-0.5",
            isCandidateOnly || isAutoRejected
              ? "text-annotation/80 italic"
              : "text-muted-foreground"
          )}
        >
          {displayName
            ? isCandidateOnly
              ? `(${displayName})`
              : displayName
            : " "}
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
        className="cursor-pointer text-muted-foreground hover:text-annotation transition-all duration-200 outline-none"
      >
        {icon}
      </button>
    </TooltipTrigger>
    <TooltipContent
      sideOffset={12}
      className="bg-popover border-border text-[11px] font-bold uppercase tracking-wide text-annotation px-2 py-1 rounded-md shadow-2xl border [&_svg]:hidden!"
    >
      {label}
    </TooltipContent>
  </Tooltip>
);
