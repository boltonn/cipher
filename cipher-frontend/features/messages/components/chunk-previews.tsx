import { Target } from "lucide-react";
import { ScoredConversationChunk } from "../types";

type ChunkSidebarItemProp = {
  chunk: ScoredConversationChunk;
  isSelected: boolean;
  onClick: () => void;
  searchMode: "text" | "semantic" | "hybrid";
};

export const ChunkSidebarItem = ({
  chunk,
  isSelected,
  onClick,
  searchMode,
}: ChunkSidebarItemProp) => (
  <button
    type="button"
    onClick={onClick}
    className={`group relative p-4 border-b border-slate-800/50 cursor-pointer transition-all text-left w-full ${
      isSelected
        ? "bg-indigo-500/10 border-l-4 border-l-indigo-500 shadow-[inset_0_0_20px_rgba(79,70,229,0.05)]"
        : "hover:bg-slate-800/30 border-l-4 border-l-transparent"
    }`}
  >
    <div className="flex justify-between items-start mb-2">
      <span
        className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${isSelected ? "bg-indigo-500 text-white" : "bg-slate-800 text-slate-500"}`}
      >
        {chunk.conversationId}
      </span>
      <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <span
          className="p-1 rounded text-indigo-400/50"
          title="Find Similar"
          aria-hidden="true"
        >
          <Target className="w-3.5 h-3.5" />
        </span>
      </div>
    </div>
    <p
      className={`text-sm mb-3 line-clamp-2 ${isSelected ? "text-slate-100" : "text-slate-400"}`}
    >
      {chunk.messages[0]?.text}
    </p>
    <div className="flex flex-wrap gap-1.5 items-center">
      {(searchMode === "semantic" || searchMode === "hybrid") &&
        chunk.score && (
          <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20 text-[10px] font-bold">
            <Target className="w-2.5 h-2.5" />
            {(chunk.score * 100).toFixed(1)}%
          </div>
        )}
      {chunk.tags &&
        chunk.tags.map((tag) => (
          <span
            key={tag}
            className="px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/20 text-[10px]"
          >
            {tag}
          </span>
        ))}
    </div>
  </button>
);
