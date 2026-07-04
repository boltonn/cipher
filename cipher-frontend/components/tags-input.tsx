"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";
import { KeyboardEvent, useState } from "react";

interface TagsInputProps {
  value: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  className?: string;
}

/** Chip-based tag input: type + Enter/comma to add, click x or Backspace to remove. */
export function TagsInput({ value, onChange, placeholder = "Add a tag...", className }: TagsInputProps) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const tag = draft.trim();
    if (tag && !value.includes(tag)) {
      onChange([...value, tag]);
    }
    setDraft("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const removeTag = (tag: string) => onChange(value.filter((t) => t !== tag));

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1.5 rounded-md border border-white/10 bg-slate-900/40 px-2 py-1.5 min-h-9 focus-within:border-indigo-500/50 transition-colors",
        className
      )}
    >
      {value.map((tag) => (
        <Badge
          key={tag}
          className="h-6 bg-indigo-500/10 text-indigo-300 border-none text-xs font-medium gap-1 px-2.5 pr-1.5"
        >
          {tag}
          <button
            type="button"
            onClick={() => removeTag(tag)}
            className="hover:text-white ml-0.5"
            aria-label={`Remove ${tag}`}
          >
            <X size={12} />
          </button>
        </Badge>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={commit}
        placeholder={value.length === 0 ? placeholder : ""}
        className="flex-1 min-w-20 bg-transparent text-sm text-slate-200 placeholder:text-slate-600 outline-none py-0.5"
      />
    </div>
  );
}
