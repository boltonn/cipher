"use client";
import { UUID } from "crypto";
import {
  CSSProperties,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useConversationContext } from "../hooks/use-conversation-context";
import type { AnnotationMode } from "../types";
import { ChunkAnnotation } from "./chunk-annotation";
import { MessageBubble } from "./message-bubble";

type ConversationThreadProps = {
  chunkId: UUID | null;
  currentQuery: string;
  annotationMode: AnnotationMode;
  activeTag: string | null;
  onTagToggle: (chunkId: UUID, tag: string, isHardNegative: boolean) => void;
  onRelevance: (chunkId: UUID, query: string, relevant: boolean) => void;
};

const scrollStyle: CSSProperties = {
  overflowAnchor: "none",
  display: "flex",
  flexDirection: "column",
};

/**
 * INTERNAL COMPONENT: ThreadContent
 * This holds the actual logic. By being separate, we can use a `key` on it
 * in the exported component to reset its internal state automatically.
 */
const ThreadContent = ({
  chunkId,
  currentQuery,
  annotationMode,
  activeTag,
  onTagToggle,
  onRelevance,
}: ConversationThreadProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const seedOffsetRef = useRef<{ offsetTop: number; scrollTop: number } | null>(
    null
  );
  const observerRef = useRef<IntersectionObserver | null>(null);
  const prevBeforeCountRef = useRef(0);

  const [contextEnabled, setContextEnabled] = useState(false);
  const [showJumpButton, setShowJumpButton] = useState(false);
  const [jumpDirection, setJumpDirection] = useState<"up" | "down">("down");

  const {
    allChunks,
    seedChunk,
    fetchPreviousPage,
    fetchNextPage,
    hasPreviousPage,
    hasNextPage,
    isFetchingPreviousPage,
    isFetchingNextPage,
    isLoadingSeed,
  } = useConversationContext(chunkId, contextEnabled);

  const autoSender = useMemo(
    () => seedChunk?.messages[0]?.sender ?? null,
    [seedChunk]
  );

  const beforeCount = chunkId
    ? allChunks.findIndex((c) => c.id === chunkId)
    : 0;
  const beforeCountSafe = beforeCount === -1 ? 0 : beforeCount;

  // 1. Initial Scroll to Seed (The "Original" working logic)
  useEffect(() => {
    if (contextEnabled || !chunkId || !seedChunk) return;
    const el = scrollRef.current;
    const target = el?.querySelector(
      `[data-chunk-id="${chunkId}"]`
    ) as HTMLElement;
    if (!el || !target) return;

    const doScroll = () => {
      if (target.offsetHeight === 0) return;
      el.scrollTop = target.offsetTop - 20;
      seedOffsetRef.current = {
        offsetTop: target.offsetTop,
        scrollTop: el.scrollTop,
      };
      setContextEnabled(true);
      ro.disconnect();
    };
    const ro = new ResizeObserver(doScroll);
    ro.observe(target);
    doScroll();
    return () => ro.disconnect();
  }, [chunkId, seedChunk, contextEnabled]);

  // 2. Scroll Restoration for Prepending (The "Original" working logic)
  useLayoutEffect(() => {
    if (
      !chunkId ||
      beforeCountSafe <= prevBeforeCountRef.current ||
      !seedOffsetRef.current
    ) {
      prevBeforeCountRef.current = beforeCountSafe;
      return;
    }

    const el = scrollRef.current;
    const target = el?.querySelector(
      `[data-chunk-id="${chunkId}"]`
    ) as HTMLElement;
    if (!el || !target) {
      prevBeforeCountRef.current = beforeCountSafe;
      return;
    }

    const { offsetTop: prevOffsetTop, scrollTop: prevScrollTop } =
      seedOffsetRef.current;
    seedOffsetRef.current = null;
    prevBeforeCountRef.current = beforeCountSafe;

    const delta = target.offsetTop - prevOffsetTop;
    el.scrollTop = prevScrollTop + delta;

    el.style.visibility = "hidden";
    requestAnimationFrame(() => {
      el.style.visibility = "";
    });
  }, [allChunks, chunkId, beforeCountSafe]);

  // 3. Jump Button Observer
  useEffect(() => {
    if (!chunkId || !contextEnabled || observerRef.current) return;
    const el = scrollRef.current;
    const target = el?.querySelector(`[data-chunk-id="${chunkId}"]`);
    if (!el || !target) return;

    observerRef.current = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          const rect = entry.boundingClientRect;
          const rootRect = entry.rootBounds;
          setJumpDirection(rect.top < (rootRect?.top ?? 0) ? "up" : "down");
          setShowJumpButton(true);
        } else {
          setShowJumpButton(false);
        }
      },
      { root: el, threshold: 0.1 }
    );
    observerRef.current.observe(target);

    return () => {
      observerRef.current?.disconnect();
      observerRef.current = null;
    };
  }, [chunkId, contextEnabled]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const { scrollTop, scrollHeight, clientHeight } = el;

    if (scrollTop < 300 && hasPreviousPage && !isFetchingPreviousPage) {
      const target = el.querySelector(
        `[data-chunk-id="${chunkId}"]`
      ) as HTMLElement;
      if (target) {
        seedOffsetRef.current = {
          offsetTop: target.offsetTop,
          scrollTop: el.scrollTop,
        };
      }
      fetchPreviousPage();
    }
    if (
      scrollHeight - scrollTop - clientHeight < 300 &&
      hasNextPage &&
      !isFetchingNextPage
    ) {
      fetchNextPage();
    }
  }, [
    chunkId,
    hasPreviousPage,
    isFetchingPreviousPage,
    hasNextPage,
    isFetchingNextPage,
    fetchPreviousPage,
    fetchNextPage,
  ]);

  if (isLoadingSeed)
    return (
      <div className="flex-1 flex items-center justify-center bg-[#0d1117]">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );

  return (
    <div className="flex-1 flex flex-col bg-[#0d1117] overflow-hidden relative">
      {showJumpButton && (
        <button
          type="button"
          onClick={() => {
            const target = scrollRef.current?.querySelector(
              `[data-chunk-id="${chunkId}"]`
            ) as HTMLElement;
            if (target)
              scrollRef.current?.scrollTo({
                top: target.offsetTop - 20,
                behavior: "smooth",
              });
          }}
          className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2 px-4 py-2 rounded-full bg-indigo-600 text-white text-sm shadow-lg"
        >
          {jumpDirection === "up" ? "↑ Jump to result" : "↓ Jump to result"}
        </button>
      )}

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto bg-[#0f1117] custom-scrollbar"
        style={scrollStyle}
      >
        <div className="px-6 space-y-12 flex flex-col items-center">
          {allChunks.map((chunk) => (
            <div
              key={chunk.id}
              data-chunk-id={chunk.id}
              className={`group relative max-w-4xl w-full py-12 px-10 rounded-[3rem] border transition-colors ${chunk.id === chunkId ? "bg-indigo-500/5 border-indigo-500/30" : "bg-slate-900/10 border-slate-800/40"}`}
            >
              <ChunkAnnotation
                chunkId={chunk.id}
                currentQuery={currentQuery}
                annotationMode={annotationMode}
                activeTag={activeTag}
                onTagToggle={onTagToggle}
                onRelevance={onRelevance}
              >
                <div className="flex flex-col">
                  {chunk.messages.map((msg, i) => (
                    <div
                      key={msg.messageId}
                      className={
                        (!chunk.messages[i - 1] ||
                          chunk.messages[i - 1].sender !== msg.sender) &&
                        i !== 0
                          ? "mt-4"
                          : "mt-1"
                      }
                    >
                      <MessageBubble
                        message={msg}
                        isSender={msg.sender === autoSender}
                        showSender={
                          !chunk.messages[i - 1] ||
                          chunk.messages[i - 1].sender !== msg.sender
                        }
                      />
                    </div>
                  ))}
                </div>
              </ChunkAnnotation>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// EXPORT: We wrap the content and give it a KEY based on chunkId.
// When chunkId changes, the entire internal component unmounts and remounts.
// This handles all the "Reset state" logic without the "cascading render" error.
export const ConversationThread = (props: ConversationThreadProps) => {
  return <ThreadContent key={props.chunkId ?? "empty"} {...props} />;
};
