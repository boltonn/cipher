"use client";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { facesService } from "@/features/faces/api";
import { getFaceCoverStyle } from "@/features/faces/components/face-crop";
import { useSetFaceRepresentative } from "@/features/faces/hooks/use-set-representative";
import { FacePublic } from "@/features/faces/types";
import { PersonExampleUploadButton } from "@/features/persons/components/person-example-upload-button";
import { cn } from "@/lib/utils";
import { ChevronLeft, ChevronRight, Loader2, Plus, Star } from "lucide-react";
import { useEffect, useState } from "react";

const MAX_EXAMPLES = 10;
const HERO_HEIGHT = 260;
const HERO_WIDTH = 220;
const HERO_ASPECT_RATIO = HERO_WIDTH / HERO_HEIGHT;
const THUMB_SIZE = 80;

interface PersonExamplesGalleryProps {
  personId: string;
  faces: FacePublic[];
  isPending?: boolean;
}

export function PersonExamplesGallery({ personId, faces, isPending }: PersonExamplesGalleryProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const setRepresentative = useSetFaceRepresentative();

  // Clamp as a derived value instead of correcting state in an effect --
  // `faces` can shrink/grow (add/delete example) out from under a stale index.
  const safeIndex = faces.length > 0 ? Math.min(selectedIndex, faces.length - 1) : 0;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (faces.length <= 1) return;
      if (e.key === "ArrowRight") setSelectedIndex((i) => (i + 1) % faces.length);
      if (e.key === "ArrowLeft") setSelectedIndex((i) => (i - 1 + faces.length) % faces.length);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [faces.length]);

  const selected = faces[safeIndex] as FacePublic | undefined;
  const atCap = faces.length >= MAX_EXAMPLES;

  if (isPending) {
    return <Loader2 size={16} className="animate-spin text-muted-foreground" />;
  }

  return (
    <div className="flex items-start gap-3">
      {/* Thumbnail rail -- vertical only. The extra pr-4 reserves room for
          the vertical scrollbar (when present) so it doesn't eat into the
          fixed-width thumbnails and clip them; overflow-x-hidden is a
          backstop against any residual horizontal scrollbar. */}
      <div
        className="flex flex-col gap-2 pr-4 overflow-y-auto overflow-x-hidden shrink-0"
        style={{ width: THUMB_SIZE + 16, maxHeight: HERO_HEIGHT }}
      >
        {faces.map((face, i) => (
          <button
            key={face.id}
            type="button"
            onClick={() => setSelectedIndex(i)}
            style={{
              width: THUMB_SIZE,
              height: THUMB_SIZE,
              ...getFaceCoverStyle(face.boundingBox, facesService.getFaceViewUrl(face.id), 1),
            }}
            className={cn(
              "relative rounded-lg overflow-hidden shrink-0 border-2 bg-muted transition-all bg-cover bg-center",
              i === safeIndex
                ? "border-annotation shadow-[0_0_12px_rgba(245,158,11,0.4)]"
                : "border-border hover:border-white/30"
            )}
          >
            {face.isPrimary && (
              <span className="absolute bottom-1 right-1 h-4 w-4 rounded-full bg-annotation flex items-center justify-center ring-1 ring-black/50">
                <Star size={9} className="text-black" fill="black" />
              </span>
            )}
          </button>
        ))}

        <PersonExampleUploadButton
          personId={personId}
          atCap={atCap}
          style={{ width: THUMB_SIZE, height: THUMB_SIZE }}
          busyIcon={<Loader2 size={18} className="animate-spin" />}
          className="rounded-lg border-2 border-dashed border-border hover:border-annotation/50 flex items-center justify-center text-muted-foreground hover:text-annotation transition-colors shrink-0 disabled:opacity-30 disabled:pointer-events-none"
        >
          <Plus size={20} />
        </PersonExampleUploadButton>
      </div>

      {/* Big preview -- fixed size regardless of which face is selected;
          getFaceCoverStyle grows the crop (never stretches it) to match */}
      <div
        className="relative rounded-xl overflow-hidden bg-black group/hero shrink-0"
        style={{ height: HERO_HEIGHT, width: HERO_WIDTH }}
      >
        {selected ? (
          <>
            <div
              className="absolute inset-0 bg-cover bg-center"
              style={getFaceCoverStyle(
                selected.boundingBox,
                facesService.getFaceViewUrl(selected.id),
                HERO_ASPECT_RATIO
              )}
            />
            <div className="absolute inset-0 flex items-center justify-between px-2 pointer-events-none">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSelectedIndex((i) => (i - 1 + faces.length) % faces.length)}
                disabled={faces.length <= 1}
                className="h-9 w-9 rounded-full bg-black/40 border border-border text-white pointer-events-auto opacity-0 group-hover/hero:opacity-100 transition-all disabled:opacity-0 hover:bg-annotation/20 hover:text-annotation hover:border-annotation/50"
              >
                <ChevronLeft className="h-5 w-5" strokeWidth={1.5} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSelectedIndex((i) => (i + 1) % faces.length)}
                disabled={faces.length <= 1}
                className="h-9 w-9 rounded-full bg-black/40 border border-border text-white pointer-events-auto opacity-0 group-hover/hero:opacity-100 transition-all disabled:opacity-0 hover:bg-annotation/20 hover:text-annotation hover:border-annotation/50"
              >
                <ChevronRight className="h-5 w-5" strokeWidth={1.5} />
              </Button>
            </div>

            <TooltipProvider>
              {selected.isPrimary ? (
                <Tooltip delayDuration={200}>
                  <TooltipTrigger asChild>
                    <span className="absolute top-2.5 left-2.5 h-7 w-7 flex items-center justify-center rounded-full bg-black/60 border border-annotation/30 text-annotation">
                      <Star size={13} fill="currentColor" />
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="text-[10px]">
                    Primary photo
                  </TooltipContent>
                </Tooltip>
              ) : (
                <Tooltip delayDuration={200}>
                  <TooltipTrigger asChild>
                    <Button
                      size="icon"
                      onClick={() =>
                        setRepresentative.mutate({
                          id: selected.id,
                          data: { isRepresentative: true, isPrimary: true },
                        })
                      }
                      disabled={setRepresentative.isPending}
                      className="absolute top-2.5 left-2.5 h-7 w-7 rounded-full bg-black/60 border border-border text-foreground hover:bg-annotation/20 hover:text-annotation hover:border-annotation/40"
                    >
                      <Star size={13} />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="text-[10px]">
                    Set as primary photo
                  </TooltipContent>
                </Tooltip>
              )}
            </TooltipProvider>
          </>
        ) : (
          <PersonExampleUploadButton
            personId={personId}
            atCap={atCap}
            className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground hover:text-annotation transition-colors border-2 border-dashed border-border hover:border-annotation/40 rounded-xl disabled:opacity-30"
          >
            <Plus size={28} />
            <span className="text-xs text-center px-2">Add photo</span>
          </PersonExampleUploadButton>
        )}
      </div>
    </div>
  );
}
