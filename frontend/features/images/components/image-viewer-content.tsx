"use client";

import { cn } from "@/lib/utils";
import Image from "next/image";
import { imagesService } from "../api";
import type { ImagePublic, ImageSimilarityResult } from "../types";

interface ImageViewerContentProps {
  image: ImagePublic | ImageSimilarityResult;
  className?: string;
}

/**
 * The actual image render plus a lightweight EXIF chip strip -- shared between
 * the Images page's `ImageViewerDialog` and the generic file viewer's image
 * branch (`FileViewerContent`), so any file that's gone through the images
 * pipeline gets the same richer-than-a-bare-`<img>` treatment wherever it's
 * previewed, rather than each caller reimplementing it.
 */
export function ImageViewerContent({ image, className }: ImageViewerContentProps) {
  const chips = [
    [image.cameraMake, image.cameraModel].filter(Boolean).join(" ") || null,
    image.aperture ? `ƒ/${image.aperture}` : null,
    image.iso ? `ISO ${image.iso}` : null,
    image.focalLength ? `${image.focalLength}mm` : null,
    image.dateTaken ? new Date(image.dateTaken).toLocaleDateString() : null,
  ].filter((chip): chip is string => Boolean(chip));

  return (
    <div className={cn("relative flex-1 flex items-center justify-center p-8", className)}>
      <Image
        src={imagesService.getImageUrl(image.id)}
        alt={image.id}
        fill
        className="object-contain transition-opacity duration-300"
        unoptimized
        sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
      />
      {chips.length > 0 && (
        <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 flex-wrap justify-center gap-1.5 px-2">
          {chips.map((chip) => (
            <span
              key={chip}
              className="rounded border border-border bg-black/60 px-2 py-1 font-mono text-[10px] text-primary backdrop-blur"
            >
              {chip}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
