import { UUID } from "crypto";
import type { ScoredConversationChunk } from "./types";

const mockUUID = () =>
  "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  }) as UUID;

export function generateMockInfiniteData() {
  const items: ScoredConversationChunk[] = Array.from({ length: 15 }).map(
    (_, i) => ({
      id: mockUUID(),
      conversationId: `CONV-00${i + 1}`,
      date: new Date().toISOString(),
      score: 0.85 + Math.random() * 0.1,
      tags: [],
      hardNegativeTags: [],
      sentiment: null,
      relevance: null,
      messages: [
        {
          id: mockUUID(),
          conversationId: `CONV-00${i + 1}`,
          sender: "+1234567890",
          text: "How does the hybrid search work with the current backend?",
          dateSent: new Date().toISOString(),
        },
        {
          id: mockUUID(),
          conversationId: `CONV-00${i + 1}`,
          sender: "+0987654321",
          text: "It combines BM25 scores with dense vector similarity. It's quite efficient for large datasets.",
          dateSent: new Date().toISOString(),
        },
      ],
    })
  );
  return {
    pages: [{ items, page: 1, total: 100, limit: 15 }],
    pageParams: [1],
  };
}
