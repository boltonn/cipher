import { Chat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import { create } from "zustand";
import { baseURL } from "@/lib/api-client";
import type { JudgedSource } from "../types";

/**
 * The conversation lives outside the page, so leaving it (e.g. "Open all in search") and coming
 * back keeps the thread and the analyst's source marks. Gone on reload; "Continue in chat" or
 * Clear starts a new one.
 */
let current: Chat<UIMessage> | null = null;

/** This tab's conversation; `seed` (a hand-off from search) replaces it with a new one. */
export function sessionChat(seed?: UIMessage[]): Chat<UIMessage> {
  if (seed || !current) {
    current = new Chat({ messages: seed, transport: new DefaultChatTransport({ api: `${baseURL}/chat` }) });
  }
  return current;
}

/** The analyst's judgments on this conversation's sources, by `citationKey`. */
export const useRelevanceJudgments = create<{
  judgments: Record<string, JudgedSource>;
  setJudgments: (update: (current: Record<string, JudgedSource>) => Record<string, JudgedSource>) => void;
}>((set) => ({
  judgments: {},
  setJudgments: (update) => set((state) => ({ judgments: update(state.judgments) })),
}));
