"use client";
import { useEffect, useRef, useState } from "react";

export interface NaturalSize {
  width: number;
  height: number;
}

export interface ContainRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Tracks the actual rendered rect of an `object-contain`-fitted image within
 * its container, so overlays (bboxes, landmarks) can be positioned in pixels
 * against the visible image area instead of the container -- which may be
 * letterboxed and not share the image's aspect ratio.
 */
export function useContainRect(natural: NaturalSize | null) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setContainerSize({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  let rect: ContainRect | null = null;
  if (natural && natural.width > 0 && natural.height > 0 && containerSize.width > 0 && containerSize.height > 0) {
    const scale = Math.min(containerSize.width / natural.width, containerSize.height / natural.height);
    const width = natural.width * scale;
    const height = natural.height * scale;
    rect = {
      width,
      height,
      left: (containerSize.width - width) / 2,
      top: (containerSize.height - height) / 2,
    };
  }

  return { containerRef, rect };
}
