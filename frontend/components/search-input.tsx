"use client";

import { cn } from "@/lib/utils";
import { X } from "lucide-react";
import { useState } from "react";

interface SearchInputProps {
  /** The committed query that drives fetching. The field mirrors this when it changes externally. */
  value: string;
  /** Fired on Enter, on blur, and when the field is cleared -- never on every keystroke. */
  onSearch: (query: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  /** Also commit when the field loses focus, not just on Enter. Default true. */
  searchOnBlur?: boolean;
  className?: string;
}

/**
 * The app's default search field: the user types freely and the query is only
 * committed on Enter (or blur), so pages fetch once per intentional search
 * rather than once per keystroke. Drop it inside a `SearchBarShell`.
 */
export function SearchInput({
  value,
  onSearch,
  placeholder = "Search...",
  ariaLabel,
  searchOnBlur = true,
  className,
}: SearchInputProps) {
  const [draft, setDraft] = useState(value);
  const [lastValue, setLastValue] = useState(value);

  // Adopt an externally-changed committed value (clear-all, restored filters)
  // without an effect -- React's "adjust state during render" pattern.
  if (value !== lastValue) {
    setLastValue(value);
    setDraft(value);
  }

  const commit = (next: string) => {
    const trimmed = next.trim();
    if (trimmed !== value) onSearch(trimmed);
  };

  return (
    <>
      <input
        type="text"
        aria-label={ariaLabel}
        autoComplete="off"
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit(draft);
        }}
        onBlur={() => {
          if (searchOnBlur) commit(draft);
        }}
        className={cn(
          "w-full bg-transparent py-4 px-4 text-foreground placeholder:text-muted-foreground focus:outline-none text-sm tracking-wide",
          className
        )}
      />

      {draft && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => {
            setDraft("");
            commit("");
          }}
          className="text-muted-foreground hover:text-foreground shrink-0"
        >
          <X size={14} />
        </button>
      )}
    </>
  );
}
