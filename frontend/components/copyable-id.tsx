"use client";

import { cn } from "@/lib/utils";
import { Check, Copy } from "lucide-react";
import { useState } from "react";

interface CopyableIdProps {
  id: string;
  label?: string;
  className?: string;
}

/** Click-to-copy id, used consistently wherever a raw entity id is shown to an analyst. */
export function CopyableId({ id, label = "ID", className }: CopyableIdProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={copied ? "Copied!" : "Copy ID"}
      className={cn(
        "group/copy flex items-center gap-1.5 text-[10px] text-muted-foreground font-mono truncate hover:text-foreground transition-colors",
        className
      )}
    >
      <span className="truncate">
        {label}: {id}
      </span>
      {copied ? (
        <Check size={11} className="shrink-0 text-primary" />
      ) : (
        <Copy size={11} className="shrink-0 opacity-0 group-hover/copy:opacity-100 transition-opacity" />
      )}
    </button>
  );
}
