"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEmailConversation } from "../api";

const DATE_FORMAT: Intl.DateTimeFormatOptions = {
  day: "numeric",
  month: "short",
  year: "numeric",
};

/** The open email's conversation, oldest first, beside the message. Renders nothing for a lone email. */
export function EmailConversationRail({ fileId }: { fileId: string }) {
  const { data: conversation } = useEmailConversation(fileId);
  // keep the reader on the page they came from: the email page or the file page
  const basePath = usePathname().startsWith("/emails/") ? "/emails" : "/files";

  if (!conversation || conversation.emails.length < 2) return null;
  const senders = new Set(
    conversation.emails.map((email) => email.fromAddress ?? email.fromName)
  ).size;

  return (
    <aside className="w-64 shrink-0 flex flex-col min-h-0 border-r border-border bg-muted/20">
      <div className="shrink-0 border-b border-border px-3 py-2.5 text-xs">
        <p className="font-semibold text-foreground">Conversation</p>
        <p className="text-muted-foreground">
          {conversation.emails.length} emails · {senders}{" "}
          {senders === 1 ? "sender" : "senders"}
          {conversation.source === "quotedText" && (
            <>
              {" · "}
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="cursor-help underline decoration-dotted underline-offset-2">
                    linked by quoted text
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-64 text-xs leading-relaxed">
                  Some of these emails have no header linking them. They were
                  added because one quotes the other, with the same subject once
                  Re: / Fwd: is removed, sent within 30 days.
                </TooltipContent>
              </Tooltip>
            </>
          )}
        </p>
      </div>
      <ol className="flex-1 min-h-0 overflow-auto">
        {conversation.emails.map((email) => {
          const isOpen = email.fileId === fileId;
          return (
            <li key={email.fileId}>
              <Link
                href={`${basePath}/${email.fileId}`}
                aria-current={isOpen ? "page" : undefined}
                className={cn(
                  "block border-b border-l-2 border-b-border border-l-transparent px-3 py-2 text-xs hover:bg-muted/50",
                  isOpen && "border-l-primary bg-primary/10 hover:bg-primary/10"
                )}
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span
                    className={cn(
                      "truncate text-foreground",
                      isOpen ? "font-semibold" : "font-medium"
                    )}
                  >
                    {email.fromName || email.fromAddress || "Unknown sender"}
                  </span>
                  {email.dateSent && (
                    <span className="shrink-0 text-muted-foreground">
                      {new Date(email.dateSent).toLocaleDateString(
                        undefined,
                        DATE_FORMAT
                      )}
                    </span>
                  )}
                </span>
                <span className="mt-0.5 line-clamp-2 text-muted-foreground">
                  {email.preview || "(no text)"}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
