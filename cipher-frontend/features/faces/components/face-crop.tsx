"use client";

import type { FaceBoundingBox } from "@/features/faces/types";
import { CSSProperties } from "react";

const PAD_FACTOR = 0.4;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

interface CropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Padded crop rectangle (normalized 0-1) around a face's bounding box. */
function paddedCrop(bbox: FaceBoundingBox): CropRect {
  const padX = bbox.width * PAD_FACTOR;
  const padY = bbox.height * PAD_FACTOR;

  const width = clamp(bbox.width + padX * 2, 0.01, 1);
  const height = clamp(bbox.height + padY * 2, 0.01, 1);
  const x = clamp(bbox.x - padX, 0, 1 - width);
  const y = clamp(bbox.y - padY, 0, 1 - height);

  return { x, y, width, height };
}

function cropToStyle(crop: CropRect, imageUrl: string): CSSProperties {
  const sizeX = 100 / crop.width;
  const sizeY = 100 / crop.height;
  const posX = crop.width < 1 ? (crop.x / (1 - crop.width)) * 100 : 0;
  const posY = crop.height < 1 ? (crop.y / (1 - crop.height)) * 100 : 0;

  return {
    backgroundImage: `url(${imageUrl})`,
    backgroundSize: `${sizeX}% ${sizeY}%`,
    backgroundPosition: `${posX}% ${posY}%`,
    backgroundRepeat: "no-repeat",
  };
}

/** CSS background-position/-size to zoom a full image into a padded crop around a face's bounding box. */
export function getFaceCropStyle(bbox: FaceBoundingBox, imageUrl: string): CSSProperties {
  return cropToStyle(paddedCrop(bbox), imageUrl);
}

/**
 * Aspect ratio (width / height) of the padded crop region `getFaceCropStyle`
 * produces. `PAD_FACTOR` scales width/height proportionally so it cancels
 * out of the ratio -- this is just the bounding box's own aspect ratio.
 *
 * A container using `getFaceCropStyle` must be sized to this ratio, or the
 * background-size percentages (which scale X/Y independently) stretch the
 * image non-uniformly.
 */
export function getFaceCropAspectRatio(bbox: FaceBoundingBox): number {
  return bbox.width / bbox.height;
}

/**
 * Like `getFaceCropStyle`, but for a container with a fixed aspect ratio
 * that must stay constant across different faces (e.g. a hero preview that
 * shouldn't resize as the user pages through examples). Instead of scaling
 * X/Y independently (which distorts when the container doesn't match the
 * face's own aspect ratio), the padded crop is grown -- on whichever axis
 * is short -- to exactly match `targetAspectRatio` before computing the
 * background-size, so the scale stays uniform and nothing stretches; any
 * mismatch shows as extra surrounding context instead of distortion.
 */
export function getFaceCoverStyle(
  bbox: FaceBoundingBox,
  imageUrl: string,
  targetAspectRatio: number
): CSSProperties {
  const crop = paddedCrop(bbox);
  const cropAspect = crop.width / crop.height;

  let { x, y, width, height } = crop;
  if (cropAspect < targetAspectRatio) {
    const newWidth = clamp(height * targetAspectRatio, 0.01, 1);
    x = clamp(x - (newWidth - width) / 2, 0, 1 - newWidth);
    width = newWidth;
  } else if (cropAspect > targetAspectRatio) {
    const newHeight = clamp(width / targetAspectRatio, 0.01, 1);
    y = clamp(y - (newHeight - height) / 2, 0, 1 - newHeight);
    height = newHeight;
  }

  return cropToStyle({ x, y, width, height }, imageUrl);
}
