"use client";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useContainRect } from "@/features/faces/hooks/use-contain-rect";
import { FaceBoundingBox, FaceLandmark } from "@/features/faces/types";
import { cn } from "@/lib/utils";
import { Search } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

export interface OverlayBox {
  bbox: FaceBoundingBox;
  landmarks?: FaceLandmark[];
  isSelected?: boolean;
  label?: string;
  onClick?: () => void;
  /** Runs a "find faces similar to this one" search; renders a hover handle on the box. */
  onFindSimilar?: () => void;
  /** Identity shown on hover, e.g. "Jane Doe · matched" / "Jane Doe · potential match". */
  matchLabel?: string;
}

interface FaceImageWithOverlayProps {
  src: string;
  alt: string;
  boxes: OverlayBox[];
  className?: string;
  imageClassName?: string;
}

/**
 * Renders an image with bounding-box/landmark overlays positioned against
 * the actual rendered (object-contain) image area, not the container --
 * the container may be letterboxed and not share the image's aspect ratio.
 */
export function FaceImageWithOverlay({
  src,
  alt,
  boxes,
  className,
  imageClassName,
}: FaceImageWithOverlayProps) {
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number } | null>(null);
  const { containerRef, rect } = useContainRect(naturalSize);

  return (
    <TooltipProvider delayDuration={200}>
      <div ref={containerRef} className={cn("relative w-full h-full", className)}>
        <Image
          src={src}
          alt={alt}
          fill
          className={cn("object-contain", imageClassName)}
          unoptimized
          sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
          onLoad={(e) =>
            setNaturalSize({
              width: e.currentTarget.naturalWidth,
              height: e.currentTarget.naturalHeight,
            })
          }
        />

        {rect &&
          boxes.map((box, i) => (
            <div key={i}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div
                    role={box.onClick ? "button" : undefined}
                    tabIndex={box.onClick ? 0 : undefined}
                    onClick={box.onClick}
                    className={cn(
                      "group/box absolute border-2 shadow-[0_0_16px_rgba(245,158,11,0.5)] transition-colors",
                      box.isSelected
                        ? "border-emerald-400 shadow-[0_0_16px_rgba(52,211,153,0.6)]"
                        : "border-annotation",
                      box.onClick && "cursor-pointer hover:border-emerald-400"
                    )}
                    style={{
                      left: rect.left + box.bbox.x * rect.width,
                      top: rect.top + box.bbox.y * rect.height,
                      width: box.bbox.width * rect.width,
                      height: box.bbox.height * rect.height,
                    }}
                  >
                    {box.label && (
                      <span className="absolute -top-6 left-0 text-[11px] font-mono font-bold text-annotation bg-black/70 px-1.5 py-0.5 rounded whitespace-nowrap">
                        {box.label}
                      </span>
                    )}
                    {box.onFindSimilar && (
                      <button
                        type="button"
                        title="Find similar faces"
                        onClick={(e) => {
                          e.stopPropagation();
                          box.onFindSimilar!();
                        }}
                        className="absolute right-0 top-full mt-1 flex h-6 w-6 items-center justify-center rounded-md border border-annotation/50 bg-black/80 text-annotation opacity-0 transition-opacity group-hover/box:opacity-100 hover:bg-annotation/20"
                      >
                        <Search size={12} />
                      </button>
                    )}
                  </div>
                </TooltipTrigger>
                {box.matchLabel && (
                  <TooltipContent className="text-[11px] font-bold uppercase tracking-wide">
                    {box.matchLabel}
                  </TooltipContent>
                )}
              </Tooltip>
              {box.landmarks?.map((lm, li) => (
                <div
                  key={li}
                  className="absolute h-1.5 w-1.5 rounded-full bg-annotation shadow-[0_0_6px_rgba(245,158,11,0.9)] -translate-x-1/2 -translate-y-1/2 pointer-events-none"
                  style={{
                    left: rect.left + lm.x * rect.width,
                    top: rect.top + lm.y * rect.height,
                  }}
                  title={lm.label}
                />
              ))}
            </div>
          ))}
      </div>
    </TooltipProvider>
  );
}
