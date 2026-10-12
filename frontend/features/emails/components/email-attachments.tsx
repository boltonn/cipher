"use client";

import { Button } from "@/components/ui/button";
import { filesService } from "@/features/files/api";
import {
  FileViewerContent,
  useFileViewerData,
} from "@/features/files/components/file-viewer-content";
import type { FileRecord } from "@/features/files/types";
import { cn, formatBytes } from "@/lib/utils";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  File as FileIcon,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  Lock,
  Mail,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

const GROUP_ICONS: Record<string, LucideIcon> = {
  archive: FileArchive,
  audio: FileAudio,
  code: FileCode,
  document: FileText,
  email: Mail,
  image: FileImage,
  table: FileSpreadsheet,
  text: FileText,
  video: FileVideo,
};

interface AttachmentStripProps {
  attachments: FileRecord[];
  openId: string | null;
  onOpen: (fileId: string) => void;
}

/** The email's attachments as chips, like a mail client. */
export function AttachmentStrip({ attachments, openId, onOpen }: AttachmentStripProps) {
  if (!attachments.length) return null;
  return (
    <div className="flex max-h-24 flex-wrap items-center gap-1.5 overflow-y-auto pt-2">
      {attachments.map((file) => (
        <AttachmentChip
          key={file.id}
          file={file}
          isOpen={file.id === openId}
          onOpen={() => onOpen(file.id)}
        />
      ))}
    </div>
  );
}

function AttachmentChip({
  file,
  isOpen,
  onOpen,
}: {
  file: FileRecord;
  isOpen: boolean;
  onOpen: () => void;
}) {
  const Icon = GROUP_ICONS[file.filetypeGroup] ?? FileIcon;
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-pressed={isOpen}
      title={file.filename}
      className={cn(
        "flex max-w-64 items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors",
        isOpen
          ? "border-primary/50 bg-primary/10 text-primary"
          : "border-border bg-background hover:bg-muted/60"
      )}
    >
      <Icon size={13} className="shrink-0 text-muted-foreground" />
      <span className="truncate">{file.filename}</span>
      {file.isEncrypted && (
        <Lock size={11} className="shrink-0 text-muted-foreground" />
      )}
      <span className="shrink-0 text-[11px] text-muted-foreground">
        {formatBytes(file.size)}
      </span>
    </button>
  );
}

interface AttachmentPaneProps {
  file: FileRecord;
  index: number;
  count: number;
  onBack: () => void;
  onStep: (offset: number) => void;
}

/** One attachment's viewer in place of the email body, with a way back and through its siblings. */
export function AttachmentPane({
  file,
  index,
  count,
  onBack,
  onStep,
}: AttachmentPaneProps) {
  const item = { ...file, type: "file" as const };
  const fileUrl = filesService.getFileUrl(file.id);
  const viewerData = useFileViewerData(item, fileUrl);
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-1.5">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="h-7 gap-1.5 px-2 text-xs"
        >
          <ArrowLeft size={13} /> Back to email
        </Button>
        <span className="min-w-0 truncate text-xs font-medium">
          {file.filename}
        </span>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          {count > 1 && (
            <>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-7"
                disabled={index === 0}
                onClick={() => onStep(-1)}
                aria-label="Previous attachment"
              >
                <ChevronLeft size={14} />
              </Button>
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {index + 1} of {count}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-7"
                disabled={index === count - 1}
                onClick={() => onStep(1)}
                aria-label="Next attachment"
              >
                <ChevronRight size={14} />
              </Button>
            </>
          )}
          <Button asChild variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs">
            <Link href={`/files/${file.id}`}>
              <ExternalLink size={13} /> Open file page
            </Link>
          </Button>
          <Button asChild variant="ghost" size="icon" className="size-7">
            <a href={fileUrl} download={file.filename} aria-label="Download">
              <Download size={14} />
            </a>
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <FileViewerContent
          key={file.id}
          file={item}
          fileUrl={fileUrl}
          sidebarFitsInline={false}
          {...viewerData}
        />
      </div>
    </div>
  );
}
