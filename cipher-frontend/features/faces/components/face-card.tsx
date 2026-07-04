"use client";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { facesService } from "@/features/faces/api";
import { FacePublic, FaceSimilarityResult } from "@/features/faces/types";
import { usePerson } from "@/features/persons/hooks/use-persons";
import { cn } from "@/lib/utils";
import { BadgeCheck, Maximize2, ScanFace, Search, Sparkles, UserCheck, UserPlus } from "lucide-react";
import { getFaceCropStyle } from "./face-crop";

interface FaceCardProps {
  face: FacePublic | FaceSimilarityResult;
  onFindSimilar?: (id: string) => void;
  onExpand?: (face: FacePublic) => void;
  onCreatePerson?: (face: FacePublic) => void;
}

export const FaceCard: React.FC<FaceCardProps> = ({ face, onFindSimilar, onExpand, onCreatePerson }) => {
  const imageUrl = facesService.getFaceViewUrl(face.id);
  const cropStyle = getFaceCropStyle(face.boundingBox, imageUrl);
  const { data: person } = usePerson(face.personId);
  const similarityScore = "similarityScore" in face ? face.similarityScore : undefined;

  const isCandidateOnly = face.status === "matched" && !face.personId && !!face.candidatePersonName;
  const displayName = face.personId ? person?.name : face.candidatePersonName;

  return (
    <TooltipProvider>
      <div className="group relative rounded-xl overflow-hidden bg-slate-900/40 border border-white/5 transition-all duration-300 hover:border-indigo-500/40 hover:bg-slate-900/60">
        <div
          role="button"
          tabIndex={0}
          className="aspect-square relative w-full bg-background cursor-pointer"
          style={cropStyle}
          onClick={() => onExpand?.(face)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onExpand?.(face);
            }
          }}
        >
          <div className="absolute inset-x-0 bottom-3 flex justify-center opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-300 z-10">
            <div
              className="flex items-center gap-4 bg-popover/95 border border-white/10 px-4 py-2 rounded-full shadow-2xl"
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
            <span className="absolute top-2 left-2 text-[9px] font-mono font-bold text-annotation bg-annotation/10 border border-annotation/30 px-1.5 py-0.5 rounded backdrop-blur-sm">
              {(similarityScore * 100).toFixed(0)}% match
            </span>
          )}
        </div>

        <div className="p-2.5 border-t border-white/5 space-y-1">
          {face.status === "verified" ? (
            <Badge className="text-[9px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 w-full justify-start bg-indigo-500/10 text-indigo-400">
              <BadgeCheck size={10} className="shrink-0" />
              Verified
            </Badge>
          ) : face.status === "matched" ? (
            <Badge
              className={cn(
                "text-[9px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 w-full justify-start",
                isCandidateOnly ? "bg-annotation/10 text-annotation" : "bg-indigo-500/10 text-indigo-400"
              )}
            >
              {isCandidateOnly ? <Sparkles size={10} className="shrink-0" /> : <UserCheck size={10} className="shrink-0" />}
              Matched
            </Badge>
          ) : (
            <Badge className="text-[9px] font-bold uppercase tracking-tight border-none px-1.5 py-0.5 gap-1 bg-white/5 text-slate-500 w-full justify-start">
              <ScanFace size={10} className="shrink-0" />
              Unmatched
            </Badge>
          )}
          {displayName && (
            <p
              className={cn(
                "text-[10px] truncate px-0.5",
                isCandidateOnly ? "text-annotation/80 italic" : "text-slate-400"
              )}
            >
              {isCandidateOnly ? `(${displayName})` : displayName}
            </p>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
};

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
        className="cursor-pointer text-slate-400 hover:text-annotation transition-all duration-200 hover:drop-shadow-[0_0_8px_rgba(245,158,11,0.8)] outline-none"
      >
        {icon}
      </button>
    </TooltipTrigger>
    <TooltipContent
      sideOffset={12}
      className="bg-popover border-white/10 text-[9px] font-bold uppercase tracking-widest text-annotation px-2 py-1 rounded-md shadow-2xl border [&_svg]:hidden!"
    >
      {label}
    </TooltipContent>
  </Tooltip>
);
