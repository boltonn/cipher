"use client";

import { imagesService } from "@/features/images/api";
import { ImageOff } from "lucide-react";
import { useState } from "react";

/** A square image tile that opens similar images; an image that won't load shows a quiet placeholder. */
export function ImageThumb({ imageId, onOpen }: { imageId: string; onOpen: () => void }) {
  const [failed, setFailed] = useState(false);
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label="Find similar images"
      className="grid aspect-square place-items-center overflow-hidden rounded-md border border-border bg-muted"
    >
      {failed ? (
        <ImageOff className="size-4 text-muted-foreground" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- API-served thumbnails, not static assets
        <img
          src={imagesService.getImageUrl(imageId)}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
          className="size-full object-cover transition-transform hover:scale-105"
        />
      )}
    </button>
  );
}
