import { useLayoutEffect, useRef } from "react";

const positions = new Map<string, number>();

/**
 * Remember how far down the page each search was scrolled, and put it back when you return to it
 * (Back, a trail step). The app scrolls inside the layout's `[data-page-scroll]` element, not the
 * window, so the browser's own scroll restoration doesn't cover it.
 */
export function useRememberedScroll<T extends HTMLElement>(key: string) {
  const ref = useRef<T>(null);
  useLayoutEffect(() => {
    const root = ref.current?.closest<HTMLElement>("[data-page-scroll]");
    if (!root) return;
    root.scrollTop = positions.get(key) ?? 0;
    const save = () => positions.set(key, root.scrollTop);
    root.addEventListener("scroll", save, { passive: true });
    return () => root.removeEventListener("scroll", save);
  }, [key]);
  return ref;
}
