"use client";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ApiKeyDialog } from "@/features/chat/components/api-key-dialog";
import { ChatInput } from "@/features/chat/components/chat-input";
import { ChatMessages } from "@/features/chat/components/chat-messages";
import type { ChatCitation } from "@/features/chat/types";
// Import both hooks from your store file
import {
  useChatStore,
  useChatStoreHydrated,
} from "@/features/chat/hooks/use-chat-store";
import { useFile } from "@/features/files/api";
import { FileViewerDialog } from "@/features/files/components/file-viewer-dialog";
import type { FileBrowserItem, FileLocationTarget } from "@/features/files/types";
import { baseURL } from "@/lib/api-client";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { ChevronDownIcon } from "lucide-react";
import { useState } from "react";

// Matches the backend's TRACE_MARKER in api/routes/chat.py -- splits a message's short
// summary from the full traceback appended after it, so the trace can render collapsed.
const TRACE_MARKER = "---TRACEBACK---";

function splitErrorTrace(message: string): { summary: string; trace?: string } {
  const index = message.indexOf(TRACE_MARKER);
  if (index === -1) return { summary: message };
  return {
    summary: message.slice(0, index).trim(),
    trace: message.slice(index + TRACE_MARKER.length).trim(),
  };
}

export default function ChatPage() {
  const { keys, model, datasetId, setDatasetId } = useChatStore();
  const isStoreHydrated = useChatStoreHydrated(); // Reusable hydration state
  const [keyDialogOpen, setKeyDialogOpen] = useState(false);
  const [openCitation, setOpenCitation] = useState<ChatCitation | null>(null);
  const { data: citationFile } = useFile(openCitation?.fileId);
  const citationBrowserItem: FileBrowserItem | null = citationFile
    ? { ...citationFile, type: "file" }
    : null;
  const citationLocationTarget: FileLocationTarget | undefined = openCitation
    ? {
        pageNumber: openCitation.pageNumber,
        startOffset: openCitation.startOffset,
        endOffset: openCitation.endOffset,
      }
    : undefined;

  // Clean dynamic string lookup based on your store state
  const currentProvider = model.split(":")[0];
  // The local provider talks to an unauthenticated on-machine server -- no key needed.
  const currentApiKey =
    currentProvider === "local" ? "local" : keys[currentProvider];

  const {
    messages,
    sendMessage,
    setMessages,
    stop,
    status,
    error,
    clearError,
  } = useChat({
    transport: new DefaultChatTransport({
      api: `${baseURL}/chat`,
    }),
  });

  const isLoading = status === "submitted" || status === "streaming";
  const lastMessage = messages[messages.length - 1];
  const lastMessageHasText =
    lastMessage?.role === "assistant" &&
    lastMessage.parts.some((part) => part.type === "text" && part.text.length > 0);
  const showLoadingIndicator = isLoading && !(status === "streaming" && lastMessageHasText);

  const handleSubmit = (message: PromptInputMessage) => {
    if (!currentApiKey) return;
    clearError();

    sendMessage(
      { text: message.text },
      {
        headers: {
          "x-api-key": currentApiKey,
        },
        body: {
          model: model,
          datasetId: datasetId,
        },
      }
    );
  };

  const handleRegenerate = () => {
    if (!currentApiKey) return;

    const lastUserIndex = [...messages]
      .reverse()
      .findIndex((m) => m.role === "user");
    if (lastUserIndex === -1) return;

    const userMessage = [...messages].reverse()[lastUserIndex];
    const text = userMessage.parts
      .filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("");

    if (!text) return;

    clearError();
    setMessages(messages.slice(0, messages.length - lastUserIndex));
    sendMessage(
      { text },
      {
        headers: {
          "x-api-key": currentApiKey,
        },
        body: {
          model: model,
          datasetId: datasetId,
        },
      }
    );
  };

  const handleClear = () => {
    stop();
    setMessages([]);
    clearError();
  };

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto px-4 py-6">
      <div className="flex-1 overflow-y-auto min-h-0 space-y-4">
        <ChatMessages messages={messages} onRegenerate={handleRegenerate} onOpenCitation={setOpenCitation} />

        {/* Animated Three-Dot Loader on the System/AI Side */}
        {showLoadingIndicator && (
          <div className="flex items-start gap-3 px-4 py-2 max-w-[85%] mr-auto">
            <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center shrink-0 border text-xs font-medium">
              AI
            </div>
            <div className="bg-muted text-muted-foreground rounded-2xl px-4 py-3 shadow-sm flex items-center gap-1 min-h-10">
              <span className="w-2 h-2 bg-foreground/50 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
              <span className="w-2 h-2 bg-foreground/50 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
              <span className="w-2 h-2 bg-foreground/50 rounded-full animate-bounce"></span>
            </div>
          </div>
        )}
      </div>

      {/* Reusable hook guards this to ensure zero flashes */}
      {isStoreHydrated && !currentApiKey && (
        <Alert variant="destructive" className="mb-2 mt-4">
          <AlertDescription className="flex items-center justify-between">
            <span>No API key configured for {currentProvider}.</span>
            <button
              type="button"
              onClick={() => setKeyDialogOpen(true)}
              className="underline hover:no-underline text-xs ml-4 shrink-0"
            >
              Add key
            </button>
          </AlertDescription>
        </Alert>
      )}

      {error &&
        (() => {
          const { summary, trace } = splitErrorTrace(error.message ?? "Something went wrong.");
          return (
            <Alert variant="destructive" className="mb-2 mt-4">
              <AlertDescription className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span>{summary}</span>
                  <div className="flex items-center gap-3 shrink-0 ml-4">
                    <button
                      type="button"
                      onClick={handleRegenerate}
                      className="underline hover:no-underline text-xs"
                    >
                      Retry
                    </button>
                    <button
                      type="button"
                      onClick={clearError}
                      className="text-xs opacity-60 hover:opacity-100"
                    >
                      ✕
                    </button>
                  </div>
                </div>
                {trace && (
                  <Collapsible className="group">
                    <CollapsibleTrigger className="flex w-fit items-center gap-1 text-xs text-destructive/80 hover:text-destructive">
                      Show traceback
                      <ChevronDownIcon className="h-3 w-3 transition-transform group-data-[state=open]:rotate-180" />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="mt-1.5">
                      <pre className="max-h-64 overflow-auto rounded-md bg-black/30 p-2 text-[11px] whitespace-pre-wrap">
                        {trace}
                      </pre>
                    </CollapsibleContent>
                  </Collapsible>
                )}
              </AlertDescription>
            </Alert>
          );
        })()}

      <ApiKeyDialog open={keyDialogOpen} onOpenChange={setKeyDialogOpen} />

      <FileViewerDialog
        file={citationBrowserItem}
        isOpen={!!openCitation}
        onOpenChange={(open) => {
          if (!open) setOpenCitation(null);
        }}
        hasNext={false}
        hasPrev={false}
        locationTarget={citationLocationTarget}
      />

      <ChatInput
        status={status}
        onSubmit={handleSubmit}
        onStop={stop}
        onClear={handleClear}
        messages={messages}
        datasetId={datasetId}
        onDatasetIdChange={setDatasetId}
      />
    </div>
  );
}
