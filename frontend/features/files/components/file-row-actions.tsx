"use client";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Check, Copy, Download, Eye } from "lucide-react";
import { useState } from "react";
import { filesService } from "../api";
import type { FileBrowserItem } from "../types";

interface FileRowActionsProps {
  file: FileBrowserItem;
  onView: (file: FileBrowserItem) => void;
  className?: string;
}

/** View/Download/Copy-ID icon row for a file, used by both the Tree and Table views. */
export function FileRowActions({ file, onView, className }: FileRowActionsProps) {
  const [copied, setCopied] = useState(false);

  const handleView = (e: React.MouseEvent) => {
    e.stopPropagation();
    onView(file);
  };

  const handleCopyId = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!file.id) return;
    navigator.clipboard.writeText(file.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <TooltipProvider>
      <div className={className ?? "flex items-center gap-0.5"}>
        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-primary"
              onClick={handleView}
              aria-label="View file"
            >
              <Eye size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-[9px] font-bold uppercase tracking-widest">
            View
          </TooltipContent>
        </Tooltip>

        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-primary"
              onClick={(e) => e.stopPropagation()}
              asChild
            >
              <a href={filesService.getFileUrl(file.id as string)} download={file.filename} aria-label="Download file">
                <Download size={14} />
              </a>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-[9px] font-bold uppercase tracking-widest">
            Download
          </TooltipContent>
        </Tooltip>

        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-primary"
              onClick={handleCopyId}
              aria-label="Copy file ID"
            >
              {copied ? <Check size={14} className="text-primary" /> : <Copy size={14} />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-[9px] font-bold uppercase tracking-widest">
            {copied ? "Copied!" : "Copy ID"}
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}
