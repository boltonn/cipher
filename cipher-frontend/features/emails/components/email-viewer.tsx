"use client";

import { cn } from "@/lib/utils";
import { useEffect, useRef, useState } from "react";
import type { EmailBase } from "../types";
import EmailIframe from "./email-frame";

interface EmailViewerProps {
  email: EmailBase;
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
export function EmailViewer({ email, locationTarget }: EmailViewerProps) {
  const [view, setView] = useState<"html" | "plain">(locationTarget || !email.html ? "plain" : "html");
  const markRef = useRef<HTMLElement>(null);

  // A new citation target always jumps to plain text, even if the user had
  // switched to HTML for a previous one -- mirrors search's PreviewPane,
  // which re-targets its preview the moment a new chunk is selected.
  const targetKey = locationTarget ? `${locationTarget.startOffset}-${locationTarget.endOffset}` : undefined;
  const [lastTargetKey, setLastTargetKey] = useState(targetKey);
  if (targetKey !== lastTargetKey) {
    setLastTargetKey(targetKey);
    if (targetKey) setView("plain");
  }

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [targetKey]);

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
            {email.plain ? (
              locationTarget ? (
                <>
                  {email.plain.slice(0, locationTarget.startOffset)}
                  <mark
                    ref={markRef}
                    className="rounded-[2px] bg-indigo-500/20 text-inherit shadow-[inset_0_0_0_1px_rgba(99,102,241,0.25)]"
                  >
                    {email.plain.slice(locationTarget.startOffset, locationTarget.endOffset)}
                  </mark>
                  {email.plain.slice(locationTarget.endOffset)}
                </>
              ) : (
                email.plain
              )
            ) : (
              "(no plain-text body)"
            )}
          </pre>
        )}
      </div>
    </div>
  );
}
