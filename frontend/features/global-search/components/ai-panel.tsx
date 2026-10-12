"use client";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useChatStore } from "@/features/chat/hooks/use-chat-store";
import { MessageSquare, Sparkles, Wand2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSearchAssist } from "../api";
import { handOff } from "../handoff";
import type { OverviewRequest, OverviewResponse } from "../types";
import { NameChoices } from "./name-choices";

/** Renders `[2]`-style citation markers as links to the cited file. */
function AnswerText({ answer, fileIds }: { answer: string; fileIds: Map<number, string> }) {
  const parts = answer.split(/(\[\d+\])/g);
  return (
    <p className="text-sm leading-relaxed text-foreground">
      {parts.map((part, index) => {
        const number = /^\[(\d+)\]$/.exec(part)?.[1];
        const fileId = number ? fileIds.get(Number(number)) : undefined;
        return fileId ? (
          <Link key={index} href={`/files/${fileId}`} className="font-medium text-annotation hover:underline">
            {part}
          </Link>
        ) : (
          <span key={index}>{part}</span>
        );
      })}
    </p>
  );
}

interface AiPanelProps {
  overview: OverviewResponse;
  onApply: (request: OverviewRequest) => void;
}

/** AI help for a results page (answer + suggested narrower search), loaded after the results; amber = AI. */
export function AiPanel({ overview, onApply }: AiPanelProps) {
  const router = useRouter();
  const { layout, request, searchId } = overview;
  const { data: assist, isPending, isError } = useSearchAssist(searchId, !!request.query);
  const setChatDatasets = useChatStore((state) => state.setDatasetIds);

  if (!request.query) return null;
  if (isPending) {
    if (!layout.isQuestion) return null;
    return (
      <section className="rounded-xl border border-annotation/30 bg-annotation/5 p-4">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-annotation">
          <Sparkles className="size-3.5" /> Reading the top results…
        </p>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="mt-2 h-4 w-1/2" />
      </section>
    );
  }
  if (isError) {
    return layout.isQuestion ? (
      <p className="text-xs text-muted-foreground">The AI answer is unavailable right now; the results below are unaffected.</p>
    ) : null;
  }
  const nameChoices = assist.nameChoices ?? [];
  if (!assist.answer && !assist.suggestion && nameChoices.length === 0) return null;

  const fileIds = new Map(assist.citations.map((citation) => [citation.number, citation.fileId]));

  const continueInChat = () => {
    setChatDatasets(request.datasetIds);
    handOff({ target: "chat", query: request.query, answer: assist.answer ?? "", citations: assist.citations });
    router.push("/chat");
  };

  return (
    <section className="space-y-3 rounded-xl border border-annotation/30 bg-annotation/5 p-4">
      {assist.answer && (
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-xs font-medium text-annotation">
            <Sparkles className="size-3.5" /> AI answer from the top results — check the sources
          </p>
          <AnswerText answer={assist.answer} fileIds={fileIds} />
          {assist.citations.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {assist.citations.map((citation) => (
                <Link
                  key={citation.chunkId}
                  href={`/files/${citation.fileId}`}
                  className="inline-flex h-6 max-w-72 items-center rounded-full border border-annotation/30 px-2 text-xs text-foreground hover:bg-annotation/10"
                >
                  <span className="truncate">{citation.title}</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
      {nameChoices.length > 0 && (
        <NameChoices
          choices={nameChoices}
          onSearch={(entityGroups) =>
            onApply({
              ...request,
              filters: { ...request.filters, entityGroups: [...(request.filters.entityGroups ?? []), ...entityGroups] },
              parentId: searchId,
            })
          }
        />
      )}
      <div className="flex flex-wrap items-center gap-2">
        {assist.suggestion && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1.5 border-annotation/40 text-xs hover:bg-annotation/10"
            onClick={() => onApply(assist.suggestion!.request)}
          >
            <Wand2 className="size-3.5 text-annotation" />
            Narrow to: {assist.suggestion.label}
          </Button>
        )}
        {assist.answer && (
          <Button variant="ghost" size="sm" className="h-7 gap-1.5 text-xs" onClick={continueInChat}>
            <MessageSquare className="size-3.5" /> Continue in chat
          </Button>
        )}
      </div>
    </section>
  );
}
