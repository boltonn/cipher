"use client";

import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EmailSignatureButton } from "@/features/email-signatures/components/email-signature-button";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { EmailBase, MeaningfulHashSource, QuotedBlock } from "../types";
import { EmailConversationRail } from "./email-conversation";
import EmailIframe from "./email-frame";
import { textOffsets } from "@/lib/text-offsets";
import { useEmailAttachments } from "../hooks/use-email-attachments";
import { AttachmentPane, AttachmentStrip } from "./email-attachments";

const MATCHED_BY: Record<MeaningfulHashSource, string> = {
  messageId: "the same Message-ID header",
  content:
    "the same sender, To and Cc addresses, send time, subject and opening text (it has no Message-ID)",
};

const VIEWS = [
  { value: "html", label: "HTML" },
  { value: "plain", label: "Plain text" },
] as const;

interface EmailViewerProps {
  email: EmailBase;
  /** The email's file id: shows its conversation beside the message. */
  fileId?: string;
  /** Character range into `email.plain` to highlight and scroll to -- e.g. from a chat
   * citation. Forces the plain-text view: the HTML view renders in a sandboxed iframe
   * with no same-origin access, so the parent can't scroll/highlight inside it. */
  locationTarget?: { startOffset: number; endOffset: number };
}

/**
 * Defaults to the rendered HTML view but lets the user switch to plain text,
 * which renders no iframe/images at all -- useful when offline or on a slow
 * connection, since the HTML view will otherwise sit there trying (and
 * failing) to load every remote image the email references.
 */
export function EmailViewer({
  email,
  fileId,
  locationTarget,
}: EmailViewerProps) {
  const [view, setView] = useState<"html" | "plain">(
    locationTarget || !email.html ? "plain" : "html"
  );
  const markRef = useRef<HTMLElement>(null);
  // citation offsets count code points; the text indexes UTF-16 (an emoji is two units)
  const offsets = textOffsets(email.plain ?? "");
  const target = locationTarget && {
    start: offsets.toUtf16(locationTarget.startOffset),
    end: offsets.toUtf16(locationTarget.endOffset),
  };

  // A new citation target always jumps to plain text, even if the user had
  // switched to HTML for a previous one -- mirrors search's PreviewPane,
  // which re-targets its preview the moment a new chunk is selected.
  const targetKey = locationTarget
    ? `${locationTarget.startOffset}-${locationTarget.endOffset}`
    : undefined;
  const [lastTargetKey, setLastTargetKey] = useState(targetKey);
  const [openAttachmentId, setOpenAttachmentId] = useState<string | null>(null);
  if (targetKey !== lastTargetKey) {
    setLastTargetKey(targetKey);
    if (targetKey) {
      setView("plain");
      setOpenAttachmentId(null);
    }
  }
  const [lastFileId, setLastFileId] = useState(fileId);
  if (fileId !== lastFileId) {
    setLastFileId(fileId);
    setOpenAttachmentId(null);
  }

  const attachments = useEmailAttachments(fileId, email);
  const openIndex = attachments.findIndex(
    (attachment) => attachment.id === openAttachmentId
  );

  const copies =
    email.copyFileIds?.length && email.metadata.meaningfulHashSource ? (
      <CopiesLink
        fileIds={email.copyFileIds}
        matchedBy={MATCHED_BY[email.metadata.meaningfulHashSource]}
      />
    ) : null;

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [targetKey]);

  return (
    <div className="h-full flex bg-card">
      {fileId && <EmailConversationRail fileId={fileId} />}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="shrink-0 border-b border-border bg-muted/30 p-4 text-xs text-foreground space-y-1">
          <div className="flex items-start justify-between gap-4">
            <p className="font-semibold text-sm">
              {email.metadata.title ?? "(no subject)"}
            </p>
            <div className="flex shrink-0 items-center gap-2">
              {fileId && <EmailSignatureButton fileId={fileId} />}
              {email.html && (
                <ButtonGroup className="shrink-0">
                  {VIEWS.map((option) => (
                    <Button
                      key={option.value}
                      type="button"
                      variant="outline"
                      size="sm"
                      aria-pressed={view === option.value}
                      onClick={() => {
                        setView(option.value);
                        setOpenAttachmentId(null);
                      }}
                      className={cn(
                        "h-7 border-border px-2 text-xs",
                        view === option.value
                          ? "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                          : "bg-muted/40 text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {option.label}
                    </Button>
                  ))}
                </ButtonGroup>
              )}
            </div>
          </div>
          <p>
            <span className="text-muted-foreground">From:</span>{" "}
            {email.metadata.from.name ?? email.metadata.from.value}
          </p>
          <p>
            <span className="text-muted-foreground">To:</span>{" "}
            {email.metadata.to.map((t) => t.name ?? t.value).join(", ")}
          </p>
          {(email.metadata.dateSent || copies) && (
            <p>
              {email.metadata.dateSent && (
                <>
                  <span className="text-muted-foreground">Date:</span>{" "}
                  {new Date(email.metadata.dateSent).toLocaleString()}
                </>
              )}
              {email.metadata.dateSent && copies && " · "}
              {copies}
            </p>
          )}
          <AttachmentStrip
            attachments={attachments}
            openId={openAttachmentId}
            onOpen={setOpenAttachmentId}
          />
        </div>
        <div className="flex-1 min-h-0">
          {openIndex >= 0 ? (
            <AttachmentPane
              file={attachments[openIndex]}
              index={openIndex}
              count={attachments.length}
              onBack={() => setOpenAttachmentId(null)}
              onStep={(offset) =>
                setOpenAttachmentId(attachments[openIndex + offset]?.id ?? null)
              }
            />
          ) : view === "html" ? (
            <EmailIframe body={email.html || email.plain || ""} />
          ) : (
            <pre className="h-full overflow-auto p-4 text-xs text-foreground whitespace-pre-wrap break-words font-sans">
              {email.plain ? (
                locationTarget ? (
                  <>
                    {email.plain.slice(0, target?.start)}
                    <mark
                      ref={markRef}
                      className="rounded-[2px] bg-primary/20 text-inherit shadow-[inset_0_0_0_1px_rgba(99,102,241,0.25)]"
                    >
                      {email.plain.slice(target?.start, target?.end)}
                    </mark>
                    {email.plain.slice(target?.end)}
                  </>
                ) : (
                  <QuotedPlainText
                    text={email.plain}
                    blocks={email.metadata.quotedBlocks ?? []}
                  />
                )
              ) : (
                "(no plain-text body)"
              )}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

const QUOTE_DATE_FORMAT: Intl.DateTimeFormatOptions = {
  day: "numeric",
  month: "short",
  year: "numeric",
};

function quoteLabel(block: QuotedBlock): string {
  const from = block.fromName || block.fromAddress;
  const date =
    block.dateSent &&
    new Date(block.dateSent).toLocaleDateString(undefined, QUOTE_DATE_FORMAT);
  const details = [from && `from ${from}`, date].filter(Boolean).join(", ");
  return `${block.kind === "forward" ? "Show forwarded message" : "Show quoted text"}${details ? ` (${details})` : ""}`;
}

/** Plain text with each quoted block (reply history, forwards) collapsed behind a toggle. */
function QuotedPlainText({
  text,
  blocks,
}: {
  text: string;
  blocks: QuotedBlock[];
}) {
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set());
  const offsets = textOffsets(text);
  const toggle = (index: number) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (!next.delete(index)) next.add(index);
      return next;
    });

  let cursor = 0;
  // blank lines around a quote would stack up between the toggles: they're block-level already
  const between = (from: number, to?: number) =>
    text
      .slice(from, to)
      .replace(from > 0 ? /^\s*\n/ : /^$/, "")
      .replace(/\n\s*$/, "");
  const parts: React.ReactNode[] = [];
  blocks.forEach((block, index) => {
    const start = Math.max(offsets.toUtf16(block.startOffset), cursor);
    const end = offsets.toUtf16(block.endOffset);
    if (end <= start) return;
    parts.push(between(cursor, start));
    const isOpen = expanded.has(index);
    parts.push(
      <span key={index} className="block my-1">
        <button
          type="button"
          onClick={() => toggle(index)}
          className="rounded border border-border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
        >
          {isOpen ? "Hide quoted text" : quoteLabel(block)}
        </button>
        {isOpen && (
          <span className="block border-l-2 border-border pl-3 text-muted-foreground">
            {text.slice(start, end)}
          </span>
        )}
      </span>
    );
    cursor = end;
  });
  parts.push(between(cursor));
  return <>{parts}</>;
}

/** "1 copy" / "3 copies": other files holding this same message. One opens directly; several open a list. */
function CopiesLink({
  fileIds,
  matchedBy,
}: {
  fileIds: string[];
  matchedBy: string;
}) {
  const label = `${fileIds.length} ${fileIds.length === 1 ? "copy" : "copies"}`;
  const explanation = `The same message in another file (for example the recipient's inbox and the sender's Sent folder), matched by ${matchedBy}.`;
  if (fileIds.length === 1) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Link
            href={`/files/${fileIds[0]}`}
            className="text-primary hover:underline"
          >
            {label}
          </Link>
        </TooltipTrigger>
        <TooltipContent className="max-w-64 text-xs leading-relaxed">
          {explanation}
        </TooltipContent>
      </Tooltip>
    );
  }
  return (
    <Popover>
      <PopoverTrigger className="text-primary hover:underline">
        {label}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 space-y-2 p-3 text-xs">
        <p className="text-muted-foreground leading-relaxed">{explanation}</p>
        <ul className="space-y-1">
          {fileIds.map((fileId, index) => (
            <li key={fileId}>
              <Link
                href={`/files/${fileId}`}
                className="text-primary hover:underline"
              >
                Copy {index + 1}
              </Link>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
