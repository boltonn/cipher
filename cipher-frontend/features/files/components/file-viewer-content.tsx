"use client";

import { CodeBlock } from "@/components/ai-elements/code-block";
import { Button } from "@/components/ui/button";
import { CsvViewer } from "@/components/ui/csv-viewer";
import { DocxViewerPreview } from "@/components/ui/docx-viewer";
import { PDFViewer } from "@/components/ui/pdf-viewer";
import { XlsxViewerPreview } from "@/components/ui/xlsx-viewer";
import { useEmail } from "@/features/emails/api";
import EmailIframe from "@/features/emails/components/email-frame";
import { useFileImage } from "@/features/images/api";
import { ImageViewerContent } from "@/features/images/components/image-viewer-content";
import { cn, formatBytes } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { Download, File as FileIcon, Loader2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { BundledLanguage } from "shiki";
import { getMaxPreviewBytes } from "../file-preview-limits";
import type { FileBrowserItem } from "../types";

export const TEXT_VIEWER_TYPES = new Set(["csv", "tsv"]);
export const CODE_TEXT_GROUPS = new Set(["code", "text"]);

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

/**
 * Fetches the extra data `FileViewerContent` needs beyond the file record
 * itself -- raw text for the code/csv viewers, parsed email for `.eml` --
 * shared by `FileViewerDialog` and the search preview pane so each caller
 * doesn't re-derive the same "which fetch does this filetype need" logic.
 */
export function useFileViewerData(file: FileBrowserItem | null, fileUrl?: string) {
  const isTextViewer =
    !!file && (TEXT_VIEWER_TYPES.has(file.filetype) || CODE_TEXT_GROUPS.has(file.filetypeGroup));
  const { data: textContent, isPending: isTextLoading } = useQuery({
    queryKey: ["file-text", fileUrl],
    queryFn: () => fetch(fileUrl as string).then((res) => res.text()),
    enabled: isTextViewer && !!fileUrl,
  });

  const isEmail = !!file && file.filetype === "eml";
  const { data: email, isPending: isEmailLoading } = useEmail(isEmail ? file?.id : undefined);

  return { textContent, isTextLoading, email, isEmailLoading };
}

interface FileViewerContentProps {
  file: FileBrowserItem;
  fileUrl?: string;
  textContent?: string;
  isTextLoading: boolean;
  email: import("@/features/emails/types").EmailBase | undefined;
  isEmailLoading: boolean;
  sidebarFitsInline: boolean;
  /** Query string to highlight in-place; currently only the PDF viewer's text layer supports it. */
  searchQuery?: string;
}

export function FileViewerContent({
  file,
  fileUrl,
  textContent,
  isTextLoading,
  email,
  isEmailLoading,
  sidebarFitsInline,
  searchQuery,
}: FileViewerContentProps) {
  // Only files the images pipeline has actually processed have an Image
  // record; most files won't, so this resolves to `undefined` and the plain
  // `<img>` fallback below covers everything else.
  const { data: image } = useFileImage(file.filetypeGroup === "image" ? file.id : undefined);

  if (!fileUrl) return null;

  const maxPreviewBytes = getMaxPreviewBytes(file.filetypeGroup);
  if (file.size > maxPreviewBytes) {
    return <FileTooLarge file={file} fileUrl={fileUrl} maxBytes={maxPreviewBytes} />;
  }

  if (file.filetype === "pdf") {
    return (
      <PdfWithThumbnails fileUrl={fileUrl} sidebarFitsInline={sidebarFitsInline} searchQuery={searchQuery} />
    );
  }

  if (file.filetype === "docx") {
    return <DocxViewerPreview src={fileUrl} fileName={file.filename} className="h-full" showUpload={false} />;
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
    return <EmailViewer email={email} />;
  }

  if (file.filetypeGroup === "image") {
    if (image) return <ImageViewerContent image={image} className="h-full" />;
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={fileUrl} alt={file.filename} className="w-full h-full object-contain" />;
  }

  return <ViewerFallback file={file} fileUrl={fileUrl} />;
}

/**
 * Defaults to the rendered HTML view but lets the user switch to plain text,
 * which renders no iframe/images at all -- useful when offline or on a slow
 * connection, since the HTML view will otherwise sit there trying (and
 * failing) to load every remote image the email references.
 */
function EmailViewer({ email }: { email: import("@/features/emails/types").EmailBase }) {
  const [view, setView] = useState<"html" | "plain">(email.html ? "html" : "plain");

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="shrink-0 border-b border-slate-200 bg-slate-50 p-4 text-xs text-slate-700 space-y-1">
        <div className="flex items-start justify-between gap-4">
          <p className="font-bold text-sm">{email.metadata.title ?? "(no subject)"}</p>
          {email.html && (
            <div className="shrink-0 flex rounded-md border border-slate-200 bg-white p-0.5 text-[10px] font-bold uppercase tracking-wide">
              <button
                type="button"
                onClick={() => setView("html")}
                className={cn(
                  "px-2 py-1 rounded",
                  view === "html" ? "bg-indigo-600 text-white" : "text-slate-500 hover:text-slate-800"
                )}
              >
                HTML
              </button>
              <button
                type="button"
                onClick={() => setView("plain")}
                className={cn(
                  "px-2 py-1 rounded",
                  view === "plain" ? "bg-indigo-600 text-white" : "text-slate-500 hover:text-slate-800"
                )}
              >
                Plain text
              </button>
            </div>
          )}
        </div>
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
      <div className="flex-1 min-h-0">
        {view === "html" ? (
          <EmailIframe body={email.html || email.plain || ""} />
        ) : (
          <pre className="h-full overflow-auto p-4 text-xs text-slate-800 whitespace-pre-wrap break-words font-sans">
            {email.plain || "(no plain-text body)"}
          </pre>
        )}
      </div>
    </div>
  );
}

/**
 * `PDFViewer`'s thumbnail sidebar only accepts a mount-time default (no
 * controlled open state), so it can't be toggled after render once we learn
 * the page count from `onDocumentLoadSuccess`. Instead, remount once via a
 * `key` change the first time we learn the doc is multi-page and there's
 * enough width to show the sidebar inline (not as a content-covering overlay,
 * mirroring the same width threshold the component uses internally).
 */
function PdfWithThumbnails({
  fileUrl,
  sidebarFitsInline,
  searchQuery,
}: {
  fileUrl: string;
  sidebarFitsInline: boolean;
  searchQuery?: string;
}) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const showThumbnails = numPages !== null && numPages > 1 && sidebarFitsInline;

  return (
    <PDFViewer
      key={showThumbnails ? "with-sidebar" : "no-sidebar"}
      file={fileUrl}
      className="h-full"
      defaultThumbnailSidebarOpen={showThumbnails}
      onDocumentLoadSuccess={setNumPages}
      searchQuery={searchQuery}
      showUpload={false}
    />
  );
}

export function ViewerLoading({ label }: { label: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-500 h-full">
      <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      <span className="text-[10px] font-black uppercase tracking-[0.3em] text-indigo-400/70">
        {label}
      </span>
    </div>
  );
}

function FileTooLarge({
  file,
  fileUrl,
  maxBytes,
}: {
  file: FileBrowserItem;
  fileUrl: string;
  maxBytes: number;
}) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 text-slate-400 h-full">
      <TriangleAlert className="h-16 w-16 text-slate-600" strokeWidth={1} />
      <div className="text-center space-y-1">
        <p className="text-sm text-slate-300 max-w-xs truncate">{file.filename}</p>
        <p className="text-[10px] uppercase tracking-widest text-slate-500">
          {formatBytes(file.size)} exceeds the {formatBytes(maxBytes)} preview limit
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

export function ViewerFallback({ file, fileUrl }: { file: FileBrowserItem; fileUrl: string }) {
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
