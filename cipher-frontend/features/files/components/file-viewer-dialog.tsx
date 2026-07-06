"use client";

import { CodeBlock } from "@/components/ai-elements/code-block";
import { CsvViewer } from "@/components/ui/csv-viewer";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DocxViewerPreview } from "@/components/ui/docx-viewer";
import {
  useElementWidth,
  useInlineThumbnailSidebar,
} from "@/components/ui/document-viewer-sidebar";
import { PDFViewer } from "@/components/ui/pdf-viewer";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { XlsxViewerPreview } from "@/components/ui/xlsx-viewer";

import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/copyable-id";
import { CommentSection } from "@/features/comments/components/comment-section";
import { useEmail } from "@/features/emails/api";
import EmailIframe from "@/features/emails/components/email-frame";
import { cn, formatBytes } from "@/lib/utils";
import type { BundledLanguage } from "shiki";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  File as FileIcon,
  FileText as FileTextIcon,
  HardDrive,
  Loader2,
  MessageSquare,
  ScrollText,
} from "lucide-react";
import { useState } from "react";
import { filesService, useFileText } from "../api";
import type { FileBrowserItem } from "../types";

interface FileViewerDialogProps {
  file: FileBrowserItem | null;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onNext: () => void;
  onPrev: () => void;
  hasNext: boolean;
  hasPrev: boolean;
}

const TEXT_VIEWER_TYPES = new Set(["csv", "tsv"]);
const CODE_TEXT_GROUPS = new Set(["code", "text"]);

/** Shiki's bundled language ids match most filetyper `filetype` strings directly
 * (python, javascript, json, html, ...); only the mismatches need overriding.
 * An unrecognized id just falls back to unhighlighted text at render time. */
const SHIKI_LANGUAGE_OVERRIDES: Record<string, string> = {
  h: "cpp",
  hpp: "cpp",
  batch: "bat",
  csproj: "xml",
  dockerfile: "docker",
  jsonl: "json",
  ipynb: "json",
  yml: "yaml",
};

function filetypeToShikiLanguage(file: FileBrowserItem): BundledLanguage {
  if (file.filetypeGroup === "text") return "plaintext" as BundledLanguage;
  return (SHIKI_LANGUAGE_OVERRIDES[file.filetype] ?? file.filetype) as BundledLanguage;
}

export function FileViewerDialog({
  file,
  isOpen,
  onOpenChange,
  onNext,
  onPrev,
  hasNext,
  hasPrev,
}: FileViewerDialogProps) {
  const fileUrl = file?.id ? filesService.getFileUrl(file.id) : undefined;

  const isTextViewer =
    !!file &&
    (TEXT_VIEWER_TYPES.has(file.filetype) || CODE_TEXT_GROUPS.has(file.filetypeGroup));
  const { data: textContent, isPending: isTextLoading } = useQuery({
    queryKey: ["file-text", fileUrl],
    queryFn: () => fetch(fileUrl as string).then((res) => res.text()),
    enabled: isTextViewer && !!fileUrl,
  });

  const isEmail = !!file && file.filetype === "eml";
  const { data: email, isPending: isEmailLoading } = useEmail(isEmail ? file?.id : undefined);

  if (!file) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[95vw] md:max-w-[90vw] lg:max-w-[85vw] w-full h-[92vh]
        p-0 bg-card border-white/10 overflow-hidden flex flex-col md:flex-row shadow-2xl
        ring-1 ring-white/5 gap-0"
        aria-describedby={undefined}
      >
        {/* Left: Viewer -- keyed by file so the width-measuring hook inside
            remounts fresh per file (its effect only runs once per mount) */}
        <ViewerPane
          key={file.id ?? file.path ?? file.filename}
          file={file}
          fileUrl={fileUrl}
          textContent={textContent}
          isTextLoading={isTextLoading}
          email={email}
          isEmailLoading={isEmailLoading}
          onNext={onNext}
          onPrev={onPrev}
          hasNext={hasNext}
          hasPrev={hasPrev}
        />

        {/* Right: Metadata Sidebar */}
        <aside className="w-full md:w-100 border-l border-white/5 flex flex-col bg-popover relative">
          <DialogHeader className="p-12 pb-4">
            <div className="flex items-center justify-between mb-1">
              <DialogTitle className="text-white tracking-[0.2em] uppercase text-[10px] font-black truncate">
                {file.filename}
              </DialogTitle>
              <span className="text-[10px] font-mono text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20 shrink-0 ml-2">
                {file.filetype.toUpperCase()}
              </span>
            </div>
            {file.id && <CopyableId id={file.id} />}
          </DialogHeader>

          <Separator className="bg-white/5" />

          <ScrollArea className="flex-1">
            <div className="p-4">
              <Tabs defaultValue="details" className="w-full">
                <TabsList className="w-full bg-slate-950/50 border border-white/5 h-10 p-1">
                  <TabsTrigger
                    value="details"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-indigo-600"
                  >
                    <HardDrive size={12} className="mr-2" /> Details
                  </TabsTrigger>
                  <TabsTrigger
                    value="text"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-indigo-600"
                    disabled={!file.id}
                  >
                    <ScrollText size={12} className="mr-2" /> Text
                  </TabsTrigger>
                  <TabsTrigger
                    value="comments"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-indigo-600"
                    disabled={!file.id}
                  >
                    <MessageSquare size={12} className="mr-2" /> Comments
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="details" className="mt-4">
                  <section className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-4">
                    <div className="flex items-center gap-2">
                      <FileTextIcon size={14} className="text-emerald-500" />
                      <h4 className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
                        File Metadata
                      </h4>
                    </div>
                    <div className="space-y-3">
                      <p className="text-[9px] font-mono text-slate-400 break-all">
                        {file.path ?? file.filename}
                      </p>
                      <div className="space-y-1">
                        <p className="text-[8px] text-slate-500 font-bold uppercase">
                          SHA256 Hash
                        </p>
                        <p className="text-[9px] font-mono text-emerald-500/80 break-all bg-emerald-500/5 p-1.5 rounded border border-emerald-500/10 uppercase">
                          {file.sha256}
                        </p>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <DataPoint label="Filetype" value={file.filetypeName ?? file.filetype} />
                        <DataPoint label="Type Group" value={file.filetypeGroup} />
                        <DataPoint label="Mime Type" value={file.mimeType} />
                        <DataPoint label="Storage" value={formatBytes(file.size)} />
                        {file.device && <DataPoint label="Device" value={file.device} />}
                        <DataPoint
                          label="Date Created"
                          value={
                            file.dateCreated
                              ? new Date(file.dateCreated).toLocaleDateString()
                              : "—"
                          }
                        />
                        <DataPoint
                          label="Last Updated"
                          value={
                            file.dateLastUpdated
                              ? new Date(file.dateLastUpdated).toLocaleDateString()
                              : "—"
                          }
                        />
                      </div>
                    </div>
                  </section>
                </TabsContent>

                <TabsContent value="text" className="mt-4">
                  <FileTextTab fileId={file.id} />
                </TabsContent>

                <TabsContent value="comments" className="mt-4">
                  {file.id ? (
                    <CommentSection commentableType="file" commentableId={file.id} />
                  ) : (
                    <p className="text-[10px] text-slate-600 text-center italic py-4">
                      Comments unavailable.
                    </p>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          </ScrollArea>
        </aside>
      </DialogContent>
    </Dialog>
  );
}

interface ViewerPaneProps {
  file: FileBrowserItem;
  fileUrl?: string;
  textContent?: string;
  isTextLoading: boolean;
  email: import("@/features/emails/types").EmailBase | undefined;
  isEmailLoading: boolean;
  onNext: () => void;
  onPrev: () => void;
  hasNext: boolean;
  hasPrev: boolean;
}

function ViewerPane({
  file,
  fileUrl,
  textContent,
  isTextLoading,
  email,
  isEmailLoading,
  onNext,
  onPrev,
  hasNext,
  hasPrev,
}: ViewerPaneProps) {
  const [viewerRef, viewerWidth] = useElementWidth<HTMLDivElement>();
  const sidebarFitsInline = useInlineThumbnailSidebar(viewerWidth);

  return (
    <div ref={viewerRef} className="flex-1 bg-black relative flex flex-col overflow-hidden group/viewer">
      <FileViewerContent
        file={file}
        fileUrl={fileUrl}
        textContent={textContent}
        isTextLoading={isTextLoading}
        email={email}
        isEmailLoading={isEmailLoading}
        sidebarFitsInline={sidebarFitsInline}
      />

      <div className="absolute inset-0 flex items-center justify-between px-4 pointer-events-none">
        <Button
          variant="ghost"
          size="icon"
          onClick={onPrev}
          disabled={!hasPrev}
          className={cn(
            "h-14 w-14 rounded-full bg-black/40 border border-white/10 text-white pointer-events-auto opacity-0 group-hover/viewer:opacity-100 transition-all disabled:opacity-0",
            "hover:bg-indigo-500/20 hover:text-indigo-400 hover:border-indigo-500/50"
          )}
        >
          <ChevronLeft className="h-8 w-8" strokeWidth={1.5} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onNext}
          disabled={!hasNext}
          className={cn(
            "h-14 w-14 rounded-full bg-black/40 border border-white/10 text-white pointer-events-auto opacity-0 group-hover/viewer:opacity-100 transition-all disabled:opacity-0",
            "hover:bg-indigo-500/20 hover:text-indigo-400 hover:border-indigo-500/50"
          )}
        >
          <ChevronRight className="h-8 w-8" strokeWidth={1.5} />
        </Button>
      </div>
    </div>
  );
}

interface FileViewerContentProps {
  file: FileBrowserItem;
  fileUrl?: string;
  textContent?: string;
  isTextLoading: boolean;
  email: import("@/features/emails/types").EmailBase | undefined;
  isEmailLoading: boolean;
  sidebarFitsInline: boolean;
}

function FileViewerContent({
  file,
  fileUrl,
  textContent,
  isTextLoading,
  email,
  isEmailLoading,
  sidebarFitsInline,
}: FileViewerContentProps) {
  if (!fileUrl) return null;

  if (file.filetype === "pdf") {
    return <PdfWithThumbnails fileUrl={fileUrl} sidebarFitsInline={sidebarFitsInline} />;
  }

  if (file.filetype === "docx") {
    return <DocxViewerPreview src={fileUrl} fileName={file.filename} className="h-full" />;
  }

  if (file.filetype === "xlsx") {
    return <XlsxViewerPreview src={fileUrl} fileName={file.filename} className="h-full" />;
  }

  if (TEXT_VIEWER_TYPES.has(file.filetype)) {
    if (isTextLoading) return <ViewerLoading label="Loading file..." />;
    return <CsvViewer data={textContent} className="h-full" />;
  }

  if (CODE_TEXT_GROUPS.has(file.filetypeGroup)) {
    if (isTextLoading) return <ViewerLoading label="Loading file..." />;
    if (textContent === undefined) return <ViewerFallback file={file} fileUrl={fileUrl} />;
    return (
      <div className="h-full overflow-auto p-4 bg-background">
        <CodeBlock
          code={textContent}
          language={filetypeToShikiLanguage(file)}
          showLineNumbers={file.filetypeGroup === "code"}
        />
      </div>
    );
  }

  if (file.filetype === "eml") {
    if (isEmailLoading) return <ViewerLoading label="Parsing email..." />;
    if (!email) return <ViewerFallback file={file} fileUrl={fileUrl} />;
    return (
      <div className="h-full overflow-auto bg-white">
        <div className="border-b border-slate-200 bg-slate-50 p-4 text-xs text-slate-700 space-y-1">
          <p className="font-bold text-sm">{email.metadata.title ?? "(no subject)"}</p>
          <p>
            <span className="text-slate-400">From:</span>{" "}
            {email.metadata.from.name ?? email.metadata.from.value}
          </p>
          <p>
            <span className="text-slate-400">To:</span>{" "}
            {email.metadata.to.map((t) => t.name ?? t.value).join(", ")}
          </p>
          {email.metadata.dateSent && (
            <p>
              <span className="text-slate-400">Date:</span>{" "}
              {new Date(email.metadata.dateSent).toLocaleString()}
            </p>
          )}
        </div>
        <EmailIframe body={email.html || email.plain || ""} autoSize />
      </div>
    );
  }

  if (file.filetypeGroup === "image") {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={fileUrl} alt={file.filename} className="w-full h-full object-contain" />;
  }

  return <ViewerFallback file={file} fileUrl={fileUrl} />;
}

/**
 * `PDFViewer`'s thumbnail sidebar only accepts a mount-time default (no
 * controlled open state), so it can't be toggled after render once we learn
 * the page count from `onDocumentLoadSuccess`. Instead, remount once via a
 * `key` change the first time we learn the doc is multi-page and there's
 * enough width to show the sidebar inline (not as a content-covering overlay,
 * mirroring the same width threshold the component uses internally).
 */
function PdfWithThumbnails({ fileUrl, sidebarFitsInline }: { fileUrl: string; sidebarFitsInline: boolean }) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const showThumbnails = numPages !== null && numPages > 1 && sidebarFitsInline;

  return (
    <PDFViewer
      key={showThumbnails ? "with-sidebar" : "no-sidebar"}
      file={fileUrl}
      className="h-full"
      defaultThumbnailSidebarOpen={showThumbnails}
      onDocumentLoadSuccess={setNumPages}
    />
  );
}

function FileTextTab({ fileId }: { fileId?: string }) {
  const { data, isPending, isError } = useFileText(fileId);

  if (!fileId) {
    return (
      <p className="text-[10px] text-slate-600 text-center italic py-4">Text unavailable.</p>
    );
  }
  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-slate-500">
        <Loader2 size={14} className="animate-spin" /> Loading extracted text...
      </div>
    );
  }
  if (isError || !data) {
    return (
      <p className="text-[10px] text-slate-600 text-center italic py-4">
        Not extracted yet.
      </p>
    );
  }

  return (
    <pre className="text-[10px] font-mono text-slate-300 leading-relaxed whitespace-pre-wrap break-words p-3 rounded-lg bg-black/40 border border-white/5 max-h-125 overflow-auto">
      {data.text}
    </pre>
  );
}

function ViewerLoading({ label }: { label: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-500 h-full">
      <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      <span className="text-[10px] font-black uppercase tracking-[0.3em] text-indigo-400/70">
        {label}
      </span>
    </div>
  );
}

function ViewerFallback({ file, fileUrl }: { file: FileBrowserItem; fileUrl: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 text-slate-400 h-full">
      <FileIcon className="h-16 w-16 text-slate-600" strokeWidth={1} />
      <div className="text-center space-y-1">
        <p className="text-sm text-slate-300 max-w-xs truncate">{file.filename}</p>
        <p className="text-[10px] uppercase tracking-widest text-slate-500">
          No preview available for {file.filetype || "this file type"}
        </p>
      </div>
      <a href={fileUrl} download={file.filename}>
        <Button variant="outline" size="sm" className="gap-2">
          <Download size={14} /> Download
        </Button>
      </a>
    </div>
  );
}

const DataPoint = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-0.5 min-w-0">
    <p className="text-slate-600 uppercase text-[8px] font-black tracking-widest leading-none mb-1">
      {label}
    </p>
    <p className="text-slate-200 font-mono text-[11px] truncate leading-none">{value}</p>
  </div>
);
