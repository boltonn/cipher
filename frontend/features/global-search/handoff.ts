import { create } from "zustand";
import type { GraphExpand, SearchFilters } from "@/features/search/types";
import type { AssistCitation, OverviewFilters } from "./types";

export type HandoffTarget = "text" | "images" | "entities" | "events" | "chat";

export interface SearchHandoff {
  target: HandoffTarget;
  query: string;
  datasetId?: string;
  filters?: OverviewFilters;
  /** Images: open this image's similar-images view instead of a text query. */
  imageId?: string;
  /** Chat: the AI answer the conversation continues from, and its sources. */
  answer?: string;
  citations?: AssistCitation[];
  /** Text: run exactly this search (the chat assistant's), instead of mapping overview filters. */
  chunkSearch?: ChunkSearchHandoff;
  at: number;
}

/** One of the chat assistant's searches, as `search_passages` reports it in `openAll`. */
export interface ChunkSearchHandoff {
  mode: "keyword" | "semantic" | "hybrid";
  filters: SearchFilters;
  graphExpand?: GraphExpand | null;
  /** Who `graphExpand` is about, for its filter chip. */
  graphExpandLabel?: string | null;
  datasetIds?: string[] | null;
}

const FRESH_MS = 10_000;

/**
 * "See all" from the global search page to a type page, without putting the query in the URL.
 * The target page reads it once in its state initializer. Reading doesn't clear it (React may run
 * initializers twice); it simply goes stale after a few seconds, so a later visit starts clean.
 */
const useHandoffStore = create<{ handoff: SearchHandoff | null; set: (handoff: SearchHandoff) => void }>(
  (set) => ({
    handoff: null,
    set: (handoff) => set({ handoff }),
  })
);

export function handOff(handoff: Omit<SearchHandoff, "at">) {
  useHandoffStore.getState().set({ ...handoff, at: Date.now() });
}

/** The pending handoff for `target`, if one was just made; for `useState` initializers. */
export function readHandoff(target: HandoffTarget): SearchHandoff | null {
  const handoff = useHandoffStore.getState().handoff;
  return handoff && handoff.target === target && Date.now() - handoff.at < FRESH_MS ? handoff : null;
}
