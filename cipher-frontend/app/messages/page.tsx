"use client";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { ChunkSidebarItem } from "@/features/messages/components/chunk-previews";
import { ConversationThread } from "@/features/messages/components/conversation-thread";
import { AVAILABLE_TAGS } from "@/features/messages/constants";
import { useMessageSearchController } from "@/features/messages/hooks/use-message-search-controller";
import type { AnnotationMode } from "@/features/messages/types";
import { UUID } from "crypto";
import {
  Check,
  ChevronDown,
  Filter,
  Plus,
  Search,
  Sparkles,
  Star,
  Tag,
  ThumbsDown,
  ThumbsUp,
  Type,
  X,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const SEARCH_MODE_LABELS = {
  text: "Text",
  semantic: "Semantic",
  hybrid: "Hybrid",
};
const SUGGESTED_TAGS = [
  ...AVAILABLE_TAGS.map((t) => t.toLowerCase()),
  "billing",
  "escalation",
  "dispute",
  "refund",
  "q3",
];

export default function App() {
  const [selectedChunkId, setSelectedChunkId] = useState<UUID | null>(null);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [annotationMode, setAnnotationMode] = useState<AnnotationMode>(null);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [tagPopoverOpen, setTagPopoverOpen] = useState(false);
  const [tagSearch, setTagSearch] = useState("");
  const [counts, setCounts] = useState({ positive: 0, negative: 0 });

  const { data, isPending, error, actions, searchMode, query } =
    useMessageSearchController("infinite");
  const {
    handleToggleTag,
    handleRelevance,
    handleSearch,
    handleSearchModeChange,
  } = actions;

  const allChunks = useMemo(
    () => data?.pages.flatMap((page) => ("items" in page ? page.items : [])) ?? [],
    [data]
  );

  const hasResults = allChunks.length > 0 || isPending;

  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const debouncedSearch = useCallback(
    (value: string) => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
      searchTimerRef.current = setTimeout(() => {
        if (value.trim()) handleSearch(value.trim());
      }, 500);
    },
    [handleSearch]
  );
  const sidebarRef = useRef<HTMLDivElement>(null);

  // Scroll selected sidebar item into view when navigating by keyboard
  useEffect(() => {
    if (!selectedChunkId || !sidebarRef.current) return;
    const item = sidebarRef.current.querySelector(
      `[data-sidebar-chunk-id="${selectedChunkId}"]`
    ) as HTMLElement | null;
    item?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedChunkId]);

  // ← / → keyboard navigation between chunks (disabled when typing in an input)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;

      e.preventDefault();
      if (allChunks.length === 0) return;

      const currentIndex = selectedChunkId
        ? allChunks.findIndex((c) => c.id === selectedChunkId)
        : -1;

      if (e.key === "ArrowLeft") {
        const prev =
          currentIndex <= 0 ? allChunks.length - 1 : currentIndex - 1;
        setSelectedChunkId(allChunks[prev].id);
      } else {
        const next =
          currentIndex === allChunks.length - 1 ? 0 : currentIndex + 1;
        setSelectedChunkId(allChunks[next].id);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [allChunks, selectedChunkId]);

  const enterTagMode = () => {
    setAnnotationMode("tag");
    setTagPopoverOpen(true);
  };

  const exitTagMode = () => {
    setAnnotationMode(null);
    setActiveTag(null);
    setTagPopoverOpen(false);
    setTagSearch("");
    setCounts({ positive: 0, negative: 0 });
  };

  const handleTagSelect = (tag: string) => {
    setActiveTag(tag);
    setTagPopoverOpen(false);
    setTagSearch("");
    setCounts({ positive: 0, negative: 0 });
  };

  const toggleRelevanceMode = () => {
    setAnnotationMode((prev) => {
      if (prev === "relevance") {
        setCounts({ positive: 0, negative: 0 });
        return null;
      }
      setCounts({ positive: 0, negative: 0 });
      return "relevance";
    });
  };

  const handleSearchModeChangeWithReset = (mode: typeof searchMode) => {
    if (mode !== "semantic" && annotationMode === "relevance") {
      setAnnotationMode(null);
    }
    handleSearchModeChange(mode);
  };

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen">
        <p className="text-red-500">Error: {error.message}</p>
      </div>
    );
  }

  // Toolbar tint per mode
  const toolbarClass =
    annotationMode === "tag"
      ? "bg-amber-950/40 border-amber-500/20 border-l-2 border-l-amber-500/70"
      : annotationMode === "relevance"
        ? "bg-indigo-950/50 border-indigo-500/20 border-l-2 border-l-indigo-500/70"
        : "bg-[#0f1117] border-slate-800/60";

  const annotateLabel =
    annotationMode === "tag"
      ? "text-amber-400/80"
      : annotationMode === "relevance"
        ? "text-indigo-400/80"
        : "text-slate-600";

  const canCreateTag =
    tagSearch.trim() !== "" &&
    !SUGGESTED_TAGS.some(
      (t) => t.toLowerCase() === tagSearch.trim().toLowerCase()
    );

  return (
    <div className="flex flex-col h-screen bg-[#0f1117] text-slate-200 font-sans overflow-hidden">
      {/* ── Header — search only ── */}
      <header className="h-14 border-b border-slate-800 bg-[#161b22] px-6 flex items-center gap-4 z-20 shadow-lg shrink-0">
        <span className="font-bold text-lg tracking-tight hidden md:block shrink-0">
          Messages
        </span>

        <div className="flex-1 flex items-center gap-2">
          <div className="relative flex-1 flex items-center">
            <Search className="absolute left-3 w-4 h-4 text-slate-500 pointer-events-none z-10" />
            <input
              type="text"
              aria-label="Search messages"
              value={inputValue}
              placeholder="Search messages…"
              className="w-full pl-10 pr-36 py-2 bg-slate-900/50 border border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 outline-none transition-all placeholder:text-slate-600"
              onChange={(e) => {
                setInputValue(e.target.value);
                debouncedSearch(e.target.value);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSearch(inputValue);
              }}
            />
            <div className="absolute right-2 flex items-center gap-0.5">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsFilterOpen(!isFilterOpen)}
                title="Filters"
                className={`h-7 w-7 ${isFilterOpen ? "text-indigo-400 bg-indigo-500/15 hover:bg-indigo-500/20" : "text-slate-500 hover:text-slate-300"}`}
              >
                <Filter className="w-3.5 h-3.5" />
              </Button>
              <Separator
                orientation="vertical"
                className="h-4 mx-1 bg-slate-700/80"
              />
              {(["text", "semantic", "hybrid"] as const).map((mode) => {
                const Icon =
                  mode === "text" ? Type : mode === "semantic" ? Sparkles : Zap;
                const isActive = searchMode === mode;
                return (
                  <Button
                    key={mode}
                    variant="ghost"
                    size="sm"
                    onClick={() => handleSearchModeChangeWithReset(mode)}
                    title={SEARCH_MODE_LABELS[mode]}
                    className={`h-7 gap-1 px-2 text-xs font-medium ${
                      isActive
                        ? "bg-indigo-600 text-white hover:bg-indigo-500"
                        : "text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5 shrink-0" />
                    {isActive && SEARCH_MODE_LABELS[mode]}
                  </Button>
                );
              })}
            </div>
          </div>
        </div>
      </header>

      {/* ── Contextual annotation toolbar ── */}
      {hasResults && (
        <div
          className={`h-10 border-b flex items-center gap-2 px-6 shrink-0 z-10 transition-colors duration-200 ${toolbarClass}`}
        >
          <span
            className={`text-[11px] font-semibold uppercase tracking-widest mr-1 transition-colors ${annotateLabel}`}
          >
            Annotate
          </span>

          {/* Tag mode — Popover + Command */}
          <Popover
            open={tagPopoverOpen}
            onOpenChange={(open) => {
              setTagPopoverOpen(open);
              // Opening the popover implicitly enters tag mode
              if (open && annotationMode !== "tag") setAnnotationMode("tag");
            }}
          >
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (annotationMode !== "tag") enterTagMode();
                  else setTagPopoverOpen((v) => !v);
                }}
                className={`h-7 gap-1.5 px-2.5 text-xs font-medium border transition-all ${
                  annotationMode === "tag"
                    ? "bg-amber-500/15 text-amber-300 border-amber-500/40 hover:bg-amber-500/20 hover:text-amber-200"
                    : "bg-slate-900/40 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:border-slate-600"
                }`}
              >
                <Tag className="w-3 h-3 shrink-0" />
                {annotationMode === "tag" && activeTag ? activeTag : "Tag"}
                <ChevronDown
                  className={`w-3 h-3 shrink-0 transition-transform duration-150 ${tagPopoverOpen ? "rotate-180" : ""}`}
                />
              </Button>
            </PopoverTrigger>
            <PopoverContent
              className="w-52 p-0 bg-[#1a1f2e] border-slate-700/60"
              align="start"
              sideOffset={6}
            >
              <Command className="bg-transparent">
                <CommandInput
                  placeholder="Search or create…"
                  value={tagSearch}
                  onValueChange={setTagSearch}
                  className="text-xs h-9 border-b border-slate-700/40"
                />
                <CommandList>
                  <CommandEmpty className="py-2 text-center text-xs text-slate-500">
                    No tags found
                  </CommandEmpty>
                  <CommandGroup>
                    {SUGGESTED_TAGS.map((tag) => (
                      <CommandItem
                        key={tag}
                        value={tag}
                        onSelect={() => handleTagSelect(tag)}
                        className="gap-2 text-xs text-slate-300 cursor-pointer"
                      >
                        <Tag className="w-3 h-3 text-slate-500" />
                        {tag}
                        {activeTag === tag && (
                          <Check className="w-3 h-3 ml-auto text-amber-400" />
                        )}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                  {canCreateTag && (
                    <>
                      <CommandSeparator className="bg-slate-700/40" />
                      <CommandGroup>
                        <CommandItem
                          value={`create-${tagSearch}`}
                          onSelect={() => handleTagSelect(tagSearch.trim())}
                          className="gap-2 text-xs text-amber-400 cursor-pointer"
                        >
                          <Plus className="w-3 h-3" />
                          Create {tagSearch.trim()}
                        </CommandItem>
                      </CommandGroup>
                    </>
                  )}
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>

          {/* Exit tag mode */}
          {annotationMode === "tag" && (
            <Button
              variant="ghost"
              size="icon"
              onClick={exitTagMode}
              title="Exit tag mode"
              className="h-6 w-6 text-amber-500/50 hover:text-amber-400 hover:bg-amber-500/10"
            >
              <X className="w-3.5 h-3.5" />
            </Button>
          )}

          {/* Relevance mode — semantic only */}
          {searchMode === "semantic" && (
            <>
              <Separator
                orientation="vertical"
                className="h-4 bg-slate-700/50"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={toggleRelevanceMode}
                className={`h-7 gap-1.5 px-2.5 text-xs font-medium border transition-all ${
                  annotationMode === "relevance"
                    ? "bg-indigo-500/15 text-indigo-300 border-indigo-500/40 hover:bg-indigo-500/20 hover:text-indigo-200"
                    : "bg-slate-900/40 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:border-slate-600"
                }`}
              >
                <Star className="w-3 h-3 shrink-0" />
                Relevance
              </Button>
              {annotationMode === "relevance" && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setAnnotationMode(null)}
                  title="Exit relevance mode"
                  className="h-6 w-6 text-indigo-500/50 hover:text-indigo-400 hover:bg-indigo-500/10"
                >
                  <X className="w-3.5 h-3.5" />
                </Button>
              )}
            </>
          )}

          <div className="ml-auto flex items-center gap-3">
            {/* Annotation counts — shown when a mode is active */}
            {annotationMode !== null && (
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-400">
                  <ThumbsUp size={11} strokeWidth={2} />
                  {counts.positive}
                </span>
                <span className="text-slate-700">·</span>
                <span className="flex items-center gap-1 text-[11px] font-medium text-rose-400">
                  <ThumbsDown size={11} strokeWidth={2} />
                  {counts.negative}
                </span>
              </div>
            )}
            <span
              className={`text-[11px] transition-colors ${annotationMode ? annotateLabel : "text-slate-600"}`}
            >
              {isPending ? "Searching…" : `${allChunks.length} chunks`}
            </span>
          </div>
        </div>
      )}

      {/* ── Main content ── */}
      <div className="flex flex-1 overflow-hidden">
        <aside className="w-96 flex flex-col border-r border-slate-800 bg-[#0d1117]">
          <div
            ref={sidebarRef}
            className="flex-1 overflow-y-auto custom-scrollbar"
          >
            {allChunks.map((chunk) => (
              <div key={chunk.id} data-sidebar-chunk-id={chunk.id}>
                <ChunkSidebarItem
                  chunk={chunk}
                  isSelected={selectedChunkId === chunk.id}
                  onClick={() => setSelectedChunkId(chunk.id)}
                  searchMode={searchMode}
                />
              </div>
            ))}
          </div>
        </aside>

        <ConversationThread
          chunkId={selectedChunkId}
          currentQuery={query ?? ""}
          annotationMode={annotationMode}
          activeTag={activeTag}
          onTagToggle={(chunkId, tag, isHardNegative) => {
            setCounts((c) => ({
              positive: isHardNegative ? c.positive : c.positive + 1,
              negative: isHardNegative ? c.negative + 1 : c.negative,
            }));
            handleToggleTag(chunkId, tag, isHardNegative);
          }}
          onRelevance={(chunkId, q, relevant) => {
            setCounts((c) => ({
              positive: relevant ? c.positive + 1 : c.positive,
              negative: relevant ? c.negative : c.negative + 1,
            }));
            handleRelevance(chunkId, q, relevant);
          }}
        />
      </div>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }
      `}</style>
    </div>
  );
}
