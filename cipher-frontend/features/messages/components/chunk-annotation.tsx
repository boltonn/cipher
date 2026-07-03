import { UUID } from "crypto";
import { ThumbsDown, ThumbsUp, UserPlus, X } from "lucide-react";
import { useState } from "react";
import type { AnnotationMode } from "../types";

type RelevanceState = "positive" | "negative" | null;
type AppliedTag = { tag: string; positive: boolean };

type ChunkAnnotationProps = {
  chunkId: UUID;
  currentQuery: string;
  annotationMode: AnnotationMode;
  activeTag: string | null;
  onTagToggle: (chunkId: UUID, tag: string, isHardNegative: boolean) => void;
  onRelevance: (chunkId: UUID, query: string, relevant: boolean) => void;
  children: React.ReactNode;
};

export function ChunkAnnotation({
  chunkId,
  currentQuery,
  annotationMode,
  activeTag,
  onTagToggle,
  onRelevance,
  children,
}: ChunkAnnotationProps) {
  const [appliedTags, setAppliedTags] = useState<AppliedTag[]>([]);
  const [relevance, setRelevance] = useState<RelevanceState>(null);

  const handleTagThumb = (positive: boolean) => {
    if (!activeTag) return;
    setAppliedTags((prev) => {
      const existing = prev.find((t) => t.tag === activeTag);
      if (existing) {
        return existing.positive === positive
          ? prev.filter((t) => t.tag !== activeTag)
          : prev.map((t) => (t.tag === activeTag ? { ...t, positive } : t));
      }
      return [...prev, { tag: activeTag, positive }];
    });
    onTagToggle(chunkId, activeTag, !positive);
  };

  const handleRelevanceThumb = (positive: boolean) => {
    const next: RelevanceState = positive ? "positive" : "negative";
    setRelevance((prev) => {
      if (prev === next) return null;
      onRelevance(chunkId, currentQuery, positive);
      return next;
    });
  };

  const thumbsEnabled =
    annotationMode === "relevance" ||
    (annotationMode === "tag" && activeTag !== null);
  const thumbUpActive =
    annotationMode === "relevance" && relevance === "positive";
  const thumbDownActive =
    annotationMode === "relevance" && relevance === "negative";

  // Tag applied to this chunk for activeTag (if any)
  const activeTagApplied = activeTag
    ? (appliedTags.find((t) => t.tag === activeTag) ?? null)
    : null;

  // Left bar: green = any positive annotation, red = any negative, slate = none
  const anyPositive =
    relevance === "positive" || appliedTags.some((t) => t.positive);
  const anyNegative =
    relevance === "negative" || appliedTags.some((t) => !t.positive);
  const leftBarClass =
    anyPositive && !anyNegative
      ? "bg-emerald-500"
      : anyNegative && !anyPositive
        ? "bg-rose-500"
        : anyPositive && anyNegative
          ? "bg-gradient-to-b from-emerald-500 to-rose-500"
          : "bg-slate-700/50";

  return (
    <>
      {/* Left state bar */}
      <div
        className={`absolute left-0 top-12 bottom-12 w-1.5 rounded-r-full transition-colors duration-300 ${leftBarClass}`}
      />

      {/* Right action strip */}
      <div
        className="opacity-0 group-hover:opacity-100 transition-opacity duration-150 flex flex-col gap-1.5 items-center bg-[#161b22] border border-slate-700/60 rounded-full py-2 px-1 shadow-xl absolute -right-5 top-1/2 -translate-y-1/2 z-10"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={() =>
            annotationMode === "tag"
              ? handleTagThumb(true)
              : handleRelevanceThumb(true)
          }
          disabled={!thumbsEnabled}
          className={`p-2 rounded-full transition-colors ${
            !thumbsEnabled
              ? "text-slate-700 cursor-default"
              : thumbUpActive ||
                  (annotationMode === "tag" &&
                    activeTagApplied?.positive === true)
                ? "text-emerald-400 bg-emerald-500/15"
                : "text-slate-500 hover:text-emerald-400 hover:bg-emerald-500/10"
          }`}
        >
          <ThumbsUp
            size={15}
            strokeWidth={
              thumbUpActive ||
              (annotationMode === "tag" && activeTagApplied?.positive === true)
                ? 2.5
                : 1.75
            }
          />
        </button>

        <button
          type="button"
          onClick={() =>
            annotationMode === "tag"
              ? handleTagThumb(false)
              : handleRelevanceThumb(false)
          }
          disabled={!thumbsEnabled}
          className={`p-2 rounded-full transition-colors ${
            !thumbsEnabled
              ? "text-slate-700 cursor-default"
              : thumbDownActive ||
                  (annotationMode === "tag" &&
                    activeTagApplied?.positive === false)
                ? "text-rose-400 bg-rose-500/15"
                : "text-slate-500 hover:text-rose-400 hover:bg-rose-500/10"
          }`}
        >
          <ThumbsDown
            size={15}
            strokeWidth={
              thumbDownActive ||
              (annotationMode === "tag" && activeTagApplied?.positive === false)
                ? 2.5
                : 1.75
            }
          />
        </button>

        <div className="w-5 h-px bg-slate-700/80 my-0.5" />

        <button type="button" className="p-2 rounded-full text-slate-500 hover:text-indigo-400 transition-colors">
          <UserPlus size={15} strokeWidth={1.75} />
        </button>
      </div>

      {/* Applied tag pills */}
      {appliedTags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {appliedTags.map(({ tag, positive }) => (
            <span
              key={tag}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${
                positive
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/25"
                  : "bg-rose-500/10 text-rose-400 border-rose-500/25"
              }`}
            >
              {positive ? (
                <ThumbsUp size={10} strokeWidth={2.5} />
              ) : (
                <ThumbsDown size={10} strokeWidth={2.5} />
              )}
              <span className="font-medium">{tag}</span>
              <X
                size={10}
                className="cursor-pointer opacity-50 hover:opacity-100 transition-opacity"
                onClick={() =>
                  setAppliedTags((t) => t.filter((x) => x.tag !== tag))
                }
              />
            </span>
          ))}
        </div>
      )}

      {children}
    </>
  );
}
