"use client";

import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/copyable-id";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { facesService } from "@/features/faces/api";
import { FaceImageWithOverlay } from "@/features/faces/components/face-image-overlay";
import { PotentialMatches } from "@/features/faces/components/potential-matches";
import { useAssignFace } from "@/features/faces/hooks/use-assign-face";
import { FacePublic, FaceSimilarityResult } from "@/features/faces/types";
import { PersonPicker } from "@/features/persons/components/person-picker";
import { usePerson } from "@/features/persons/hooks/use-persons";
import { cn } from "@/lib/utils";
import {
  BadgeCheck,
  ChevronLeft,
  ChevronRight,
  Compass,
  ExternalLink,
  Gauge,
  ScanFace,
  Search,
  Trash2,
  UserPlus,
  X,
} from "lucide-react";
import Link from "next/link";

interface FaceDetailDialogProps {
  face: FacePublic | FaceSimilarityResult;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onNext: () => void;
  onPrev: () => void;
  hasMore: boolean;
  hasPrev: boolean;
  onFindSimilar: (id: string) => void;
  onCreatePerson?: (face: FacePublic) => void;
  onDelete?: (id: string) => void;
}

export function FaceDetailDialog({
  face,
  isOpen,
  onOpenChange,
  onNext,
  onPrev,
  hasMore,
  hasPrev,
  onFindSimilar,
  onCreatePerson,
  onDelete,
}: FaceDetailDialogProps) {
  const assignFace = useAssignFace();
  const { data: person } = usePerson(face.personId);
  const similarityScore = "similarityScore" in face ? face.similarityScore : undefined;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[95vw] md:max-w-[90vw] lg:max-w-[85vw] w-full h-[92vh]
        p-0 bg-card border-white/10 overflow-hidden flex flex-col md:flex-row shadow-2xl
        ring-1 ring-white/5 gap-0"
        aria-describedby={undefined}
      >
        {/* Left: Source image with bbox/landmark overlay */}
        <div className="flex-1 bg-black relative flex items-center justify-center p-8 group/image min-h-0">
          <FaceImageWithOverlay
            src={facesService.getFaceViewUrl(face.id)}
            alt={face.id}
            boxes={[{ bbox: face.boundingBox, landmarks: face.landmarks }]}
          />

          <div className="absolute inset-0 flex items-center justify-between px-4 pointer-events-none">
            <Button
              variant="ghost"
              size="icon"
              onClick={onPrev}
              disabled={!hasPrev}
              className={cn(
                "h-14 w-14 rounded-full bg-black/40 border border-white/10 text-white pointer-events-auto opacity-0 group-hover/image:opacity-100 transition-all disabled:opacity-0",
                "hover:bg-annotation/20 hover:text-annotation hover:border-annotation/50"
              )}
            >
              <ChevronLeft className="h-8 w-8" strokeWidth={1.5} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onNext}
              disabled={!hasMore}
              className={cn(
                "h-14 w-14 rounded-full bg-black/40 border border-white/10 text-white pointer-events-auto opacity-0 group-hover/image:opacity-100 transition-all disabled:opacity-0",
                "hover:bg-annotation/20 hover:text-annotation hover:border-annotation/50"
              )}
            >
              <ChevronRight className="h-8 w-8" strokeWidth={1.5} />
            </Button>
          </div>
        </div>

        {/* Right: Data sidebar */}
        <aside className="w-full md:w-100 border-l border-white/5 flex flex-col bg-popover">
          <DialogHeader className="p-8 pb-4">
            <div className="flex items-center justify-between mb-1">
              <DialogTitle className="text-white tracking-[0.2em] uppercase text-[10px] font-black">
                Face Details
              </DialogTitle>
              {similarityScore != null && (
                <span className="text-[10px] font-mono text-annotation bg-annotation/10 px-2 py-0.5 rounded border border-annotation/20">
                  {(similarityScore * 100).toFixed(0)}% match
                </span>
              )}
            </div>
            <CopyableId id={face.id} />
          </DialogHeader>

          <Separator className="bg-white/5" />

          <ScrollArea className="flex-1">
            <div className="p-4 space-y-6">
              {/* Assignment */}
              <section className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-3">
                <div className="flex items-center gap-2">
                  <ScanFace size={14} className="text-annotation" />
                  <h4 className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
                    Identity
                  </h4>
                </div>
                <PersonPicker
                  value={face.personId}
                  valueName={person?.name}
                  onSelect={(personId) =>
                    assignFace.mutate({
                      id: face.id,
                      assignment: { personId, assignmentMethod: "manual" },
                    })
                  }
                />
                {face.personId && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-widest text-indigo-400">
                        {person?.isVerified && <BadgeCheck size={11} />}
                        {person?.isVerified ? "Verified" : "Matched"}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <Link
                        href={`/persons/${face.personId}`}
                        className="text-[9px] font-bold uppercase tracking-widest text-indigo-400/80 hover:text-indigo-400 flex items-center gap-1"
                      >
                        View Profile <ExternalLink size={10} />
                      </Link>
                      <button
                        type="button"
                        onClick={() =>
                          assignFace.mutate({ id: face.id, assignment: { personId: null } })
                        }
                        className="text-[9px] font-bold uppercase tracking-widest text-rose-500/60 hover:text-rose-400 flex items-center gap-1"
                      >
                        <X size={10} /> Clear
                      </button>
                    </div>
                  </div>
                )}
              </section>

              <PotentialMatches faceId={face.id} />

              {/* Detection metadata */}
              <section className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-4">
                <div className="flex items-center gap-2">
                  <Gauge size={14} className="text-indigo-500" />
                  <h4 className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
                    Detection
                  </h4>
                </div>
                <div className="grid grid-cols-2 gap-y-4 gap-x-4">
                  <DataPoint label="Model" value={face.detectorModel || "—"} />
                  <DataPoint
                    label="Confidence"
                    value={face.detectionConfidence != null ? `${(face.detectionConfidence * 100).toFixed(0)}%` : "—"}
                  />
                  <DataPoint
                    label="Quality"
                    value={face.qualityScore != null ? `${(face.qualityScore * 100).toFixed(0)}%` : "—"}
                  />
                  <DataPoint label="Landmarks" value={String(face.landmarks.length)} />
                  <DataPoint
                    label="Representative"
                    value={face.isPrimary ? "Primary" : face.isRepresentative ? "Yes" : "No"}
                  />
                </div>
              </section>

              {face.pose && (
                <section className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-4">
                  <div className="flex items-center gap-2">
                    <Compass size={14} className="text-indigo-500" />
                    <h4 className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
                      Pose
                    </h4>
                  </div>
                  <div className="grid grid-cols-3 gap-y-4 gap-x-4">
                    <DataPoint label="Yaw" value={`${face.pose.yaw.toFixed(1)}°`} />
                    <DataPoint label="Pitch" value={`${face.pose.pitch.toFixed(1)}°`} />
                    <DataPoint label="Roll" value={`${face.pose.roll.toFixed(1)}°`} />
                  </div>
                </section>
              )}
            </div>
          </ScrollArea>

          <div className="p-4 bg-slate-950/50 border-t border-white/5 flex items-center gap-2">
            <Button
              variant="outline"
              className="flex-1 h-9 text-[10px] font-bold uppercase tracking-widest border-white/10 bg-slate-900/40 text-slate-400 hover:text-annotation hover:border-annotation/40 gap-2"
              onClick={() => onFindSimilar(face.id)}
            >
              <Search size={12} /> Find Similar
            </Button>
            {onCreatePerson && (
              <Button
                variant="outline"
                className="flex-1 h-9 text-[10px] font-bold uppercase tracking-widest border-white/10 bg-slate-900/40 text-slate-400 hover:text-indigo-400 hover:border-indigo-500/40 gap-2"
                onClick={() => onCreatePerson(face)}
              >
                <UserPlus size={12} /> Create Person
              </Button>
            )}
            {onDelete && (
              <Button
                variant="outline"
                size="icon"
                className="h-9 w-9 border-white/10 bg-slate-900/40 text-slate-500 hover:text-rose-400 hover:border-rose-500/40"
                onClick={() => onDelete(face.id)}
              >
                <Trash2 size={14} />
              </Button>
            )}
          </div>
        </aside>
      </DialogContent>
    </Dialog>
  );
}

const DataPoint = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-0.5">
    <p className="text-slate-600 uppercase text-[8px] font-black tracking-widest leading-none mb-1">
      {label}
    </p>
    <p className="text-slate-200 font-mono text-[11px] truncate leading-none">{value}</p>
  </div>
);
