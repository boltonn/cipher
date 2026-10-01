"use client";

import {
  Autocomplete,
  AutocompleteContent,
  AutocompleteGroup,
  AutocompleteInput,
  AutocompleteItem,
} from "@/components/ui/autocomplete";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";
import { cn } from "@/lib/utils";
import { History, X } from "lucide-react";
import { useState } from "react";

const MAX_HISTORY = 20;
const MAX_SUGGESTIONS = 8;
const EMPTY_HISTORY: string[] = [];

interface SearchInputProps {
  /** The committed query that drives fetching. The field mirrors this when it changes externally. */
  value: string;
  /** Fired on Enter, on blur, and when the field is cleared -- never on every keystroke. */
  onSearch: (query: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  /** Also commit when the field loses focus, not just on Enter. Default true. */
  searchOnBlur?: boolean;
  /** localStorage bucket for recent searches (defaults to `ariaLabel`/`placeholder`); `false` disables history. */
  historyKey?: string | false;
  className?: string;
}

/**
 * The app's default search field: the user types freely and the query is only
 * committed on Enter (or blur), so pages fetch once per intentional search
 * rather than once per keystroke. Recent searches are remembered per field and
 * offered in the app's own suggestion menu (native browser history is off --
 * it can't be styled). Drop it inside a `SearchBarShell`.
 */
export function SearchInput({
  value,
  onSearch,
  placeholder = "Search...",
  ariaLabel,
  searchOnBlur = true,
  historyKey,
  className,
}: SearchInputProps) {
  const [draft, setDraft] = useState(value);
  const [lastValue, setLastValue] = useState(value);
  const [open, setOpen] = useState(false);
  // cmdk auto-highlights the first suggestion; Enter only picks it once the user has moved onto one.
  const [hasNavigated, setHasNavigated] = useState(false);

  const storageKey = historyKey === false ? null : `search-history:${historyKey ?? ariaLabel ?? placeholder}`;
  const [history, setHistory] = useLocalStorageState<string[]>(storageKey ?? "search-history:_", EMPTY_HISTORY);

  // Adopt an externally-changed committed value (clear-all, restored filters)
  // without an effect -- React's "adjust state during render" pattern.
  if (value !== lastValue) {
    setLastValue(value);
    setDraft(value);
  }

  const needle = draft.trim().toLowerCase();
  const suggestions = storageKey
    ? history.filter((q) => q.toLowerCase() !== needle && q.toLowerCase().includes(needle)).slice(0, MAX_SUGGESTIONS)
    : [];
  const isMenuOpen = open && suggestions.length > 0;

  const commit = (next: string) => {
    const trimmed = next.trim();
    if (trimmed && storageKey) {
      setHistory((prev) => [trimmed, ...prev.filter((q) => q !== trimmed)].slice(0, MAX_HISTORY));
    }
    if (trimmed !== value) onSearch(trimmed);
  };

  return (
    <>
      <Autocomplete
        open={isMenuOpen}
        onOpenChange={(next) => {
          setOpen(next);
          setHasNavigated(false);
        }}
        className="h-full min-w-0 flex-1"
      >
        <AutocompleteInput
          aria-label={ariaLabel}
          value={draft}
          placeholder={placeholder}
          onValueChange={(next) => {
            setDraft(next);
            setOpen(true);
            setHasNavigated(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              setHasNavigated(true);
            } else if (e.key === "Enter" && !(isMenuOpen && hasNavigated)) {
              e.preventDefault();
              commit(draft);
              setOpen(false);
            }
          }}
          onBlur={() => {
            if (searchOnBlur) commit(draft);
          }}
          className={cn(
            "h-full gap-0 rounded-none border-0 bg-transparent px-2 py-0 focus-within:ring-0",
            className
          )}
        />
        <AutocompleteContent onPointerMove={() => setHasNavigated(true)}>
          <AutocompleteGroup heading="Recent searches">
            {suggestions.map((query) => (
              <AutocompleteItem
                key={query}
                value={query}
                onSelect={() => {
                  setDraft(query);
                  commit(query);
                }}
                className={cn("group/recent", !hasNavigated && "data-[selected=true]:bg-transparent")}
              >
                <History className="text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate">{query}</span>
                <button
                  type="button"
                  aria-label={`Remove "${query}" from recent searches`}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={(e) => {
                    e.stopPropagation();
                    setHistory((prev) => prev.filter((q) => q !== query));
                  }}
                  className="text-muted-foreground opacity-0 hover:text-foreground group-hover/recent:opacity-100 group-data-[selected=true]/recent:opacity-100"
                >
                  <X className="size-3.5" />
                </button>
              </AutocompleteItem>
            ))}
          </AutocompleteGroup>
        </AutocompleteContent>
      </Autocomplete>

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
