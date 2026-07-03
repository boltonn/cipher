"use client";
import { messagesService } from "@/features/messages/api";
import { ScoredConversationChunk } from "@/features/messages/types";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { UUID } from "crypto";

type ContextPage = {
  chunks: ScoredConversationChunk[];
  cursor: string | null;
  hasMore: boolean;
};

const CONTEXT_LIMIT = 5;

export const useConversationContext = (
  chunkId: UUID | null,
  enabled: boolean
) => {
  const { data: seedData, isLoading: isLoadingSeed } = useQuery({
    queryKey: ["messages", "chunk", chunkId],
    queryFn: () => messagesService.getChunkById(chunkId!),
    enabled: !!chunkId,
  });

  const seedChunk = seedData ?? null;

  const {
    data: beforeData,
    fetchNextPage: fetchMoreBefore,
    hasNextPage: hasMoreBefore,
    isFetchingNextPage: isFetchingMoreBefore,
  } = useInfiniteQuery<ContextPage, Error>({
    queryKey: ["messages", "context", chunkId, "before"],
    queryFn: async ({ pageParam }) => {
      const chunks = await messagesService.getChunkContext(chunkId!, {
        limit: CONTEXT_LIMIT,
        cursor: pageParam as string,
        isAfter: false,
      });
      return {
        chunks,
        cursor: chunks.at(0)?.date ?? null,
        hasMore: chunks.length === CONTEXT_LIMIT,
      };
    },
    initialPageParam: seedChunk?.date,
    getNextPageParam: (lastPage) =>
      lastPage.hasMore ? lastPage.cursor : undefined,
    enabled: !!chunkId && !!seedChunk && enabled,
  });

  const {
    data: afterData,
    fetchNextPage: fetchMoreAfter,
    hasNextPage: hasMoreAfter,
    isFetchingNextPage: isFetchingMoreAfter,
  } = useInfiniteQuery<ContextPage, Error>({
    queryKey: ["messages", "context", chunkId, "after"],
    queryFn: async ({ pageParam }) => {
      const chunks = await messagesService.getChunkContext(chunkId!, {
        limit: CONTEXT_LIMIT,
        cursor: pageParam as string,
        isAfter: true,
      });
      return {
        chunks,
        cursor: chunks.at(-1)?.date ?? null,
        hasMore: chunks.length === CONTEXT_LIMIT,
      };
    },
    initialPageParam: seedChunk?.date,
    getNextPageParam: (lastPage) =>
      lastPage.hasMore ? lastPage.cursor : undefined,
    enabled: !!chunkId && !!seedChunk && enabled,
  });

  const beforeChunks = [...(beforeData?.pages ?? [])]
    .reverse()
    .flatMap((p) => p.chunks);

  const afterChunks = (afterData?.pages ?? []).flatMap((p) => p.chunks);

  const allChunks: ScoredConversationChunk[] = [
    ...beforeChunks.filter((c) => c.id !== chunkId),
    ...(seedChunk ? [seedChunk] : []),
    ...afterChunks.filter((c) => c.id !== chunkId),
  ];
  console.log(
    "[hook] allChunks ids:",
    allChunks.map((c) => c.id)
  );
  console.log(
    "[hook] beforeChunks ids:",
    beforeChunks.map((c) => c.id)
  );

  return {
    allChunks,
    seedChunk,
    fetchPreviousPage: fetchMoreBefore,
    fetchNextPage: fetchMoreAfter,
    hasPreviousPage: hasMoreBefore,
    hasNextPage: hasMoreAfter,
    isFetchingPreviousPage: isFetchingMoreBefore,
    isFetchingNextPage: isFetchingMoreAfter,
    isLoadingSeed,
  };
};
