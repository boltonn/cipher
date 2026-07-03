"use client";

import { Button } from "@/components/ui/button";
import { ImageIcon, Loader2, Search } from "lucide-react";
import React, { useRef, useState } from "react";

interface ImageSearchBarProps {
  onSearch: (query: string) => void;
  onImageUpload: (file: File) => void;
  isSearching: boolean;
}

export const ImageSearchBar: React.FC<ImageSearchBarProps> = ({
  onSearch,
  onImageUpload,
  isSearching,
}) => {
  const [inputValue, setInputValue] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = () => {
    if (inputValue.trim()) onSearch(inputValue);
  };

  return (
    <div className="w-full transition-all duration-500">
      <div
        className={`
          relative flex items-center w-full rounded-2xl border transition-all duration-500 px-4
          ${
            isSearching
              ? "bg-indigo-500/5 border-indigo-500/50 shadow-[0_0_25px_rgba(99,102,241,0.2)] ring-1 ring-indigo-500/20"
              : "bg-slate-900/40 border-white/10 hover:border-white/20 shadow-xl"
          }
        `}
      >
        <div className="flex items-center justify-center text-slate-500 pl-1">
          {isSearching ? (
            <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
          ) : (
            <Search size={18} strokeWidth={1.5} />
          )}
        </div>

        <input
          id="image-search-input"
          aria-label="Search images"
          name="query"
          type="text"
          placeholder="Type a query or drop an image..."
          className="w-full bg-transparent py-4 px-4 text-slate-100 placeholder:text-slate-600 focus:outline-none text-sm tracking-wide"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
        />

        <div className="flex items-center gap-1">
          <input
            name="image"
            type="file"
            aria-label="Upload image"
            ref={fileInputRef}
            className="hidden"
            accept="image/*"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onImageUpload(file);
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-slate-500 hover:text-indigo-400"
            onClick={() => fileInputRef.current?.click()}
          >
            <ImageIcon size={18} strokeWidth={1.5} />
          </Button>

          <div className="h-4 w-px bg-white/10 mx-2" />

          <Button
            type="button"
            variant="ghost"
            disabled={isSearching || !inputValue.trim()}
            onClick={handleSubmit}
            className={`text-[10px] font-black uppercase tracking-[0.2em] px-4 h-9 transition-all
              ${isSearching ? "text-indigo-400 animate-pulse" : "text-slate-400 hover:text-white"}
            `}
          >
            {isSearching ? "ANALYZING" : "SEARCH"}
          </Button>
        </div>
      </div>
    </div>
  );
};
