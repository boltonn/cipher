"use client";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useAgentConfig } from "@/features/chat/api";
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
import type {
  FileBrowserItem,
  FileLocationTarget,
} from "@/features/files/types";
import { useModelOptions } from "@/features/chat/hooks/use-model-options";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { baseURL } from "@/lib/api-client";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { ChevronDownIcon, MessageSquareIcon } from "lucide-react";
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
  const { keys, model: storedModel, datasetIds, setDatasetIds } = useChatStore();
  const { labelFor, effectiveModel } = useModelOptions();
  const model = effectiveModel(storedModel);
  const isStoreHydrated = useChatStoreHydrated(); // Reusable hydration state
  const [keyDialogOpen, setKeyDialogOpen] = useState(false);
  const [openCitation, setOpenCitation] = useState<ChatCitation | null>(null);
  // Navigable citations (person/dataset/entity) are <Link>s that route on their own;
  // this only ever receives passage citations, which open the file viewer at the span.
  const handleOpenCitation = (citation: ChatCitation) => {
    if (citation.fileId) setOpenCitation(citation);
  };
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

  // The server runs the agent with its own configured key (LLM__* env vars).
  // A locally-stored key is only an optional per-request override, needed only
  // when the server has no key for the selected model.
  const { data: agentConfig } = useAgentConfig();
  const currentProvider = model.split(":")[0];
  const serverHasKeyForModel =
    agentConfig?.models.find((m) => m.id === model)?.hasKey ?? false;
  // The local provider talks to an unauthenticated on-machine server -- no key needed.
  const clientKey =
    currentProvider === "local" ? "local" : keys[currentProvider];
  // Block sending only when nobody has a key for this model.
  const needsClientKey =
    currentProvider !== "local" && !serverHasKeyForModel && !clientKey;
  // Send the local key only as a fallback -- when the server has no key for
  // this model. Sending it while the server *does* have one lets a stale
  // browser key silently shadow the working server key (confusing
  // API_KEY_INVALID). Clearing the local key in model settings is the only
  // way back once that happens, so don't send it unless it's actually needed.
  const outgoingApiKey =
    currentProvider === "local" || serverHasKeyForModel
      ? undefined
      : keys[currentProvider] || undefined;

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
    lastMessage.parts.some(
      (part) => part.type === "text" && part.text.length > 0
    );
  const showLoadingIndicator =
    isLoading && !(status === "streaming" && lastMessageHasText);

  const requestOptions = () => ({
    headers: outgoingApiKey ? { "x-api-key": outgoingApiKey } : undefined,
    body: {
      model: model,
      datasetIds,
    },
  });

  const handleSubmit = (message: PromptInputMessage) => {
    if (needsClientKey) return;
    clearError();

    sendMessage({ text: message.text }, requestOptions());
  };

  const handleRegenerate = () => {
    if (needsClientKey) return;

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
    // Drop the last user message too -- sendMessage re-appends it.
    setMessages(messages.slice(0, messages.length - lastUserIndex - 1));
    sendMessage({ text }, requestOptions());
  };

  const handleClear = () => {
    stop();
    setMessages([]);
    clearError();
  };

  return (
    <div className="flex h-full w-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-sidebar/85 px-4 backdrop-blur-xl">
        <SidebarTrigger className="h-9 w-9 text-muted-foreground hover:text-primary" />
        <div className="flex flex-col">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Assistant
          </span>
          <span className="flex items-center gap-1.5 font-mono text-xs text-primary/80">
            <MessageSquareIcon className="h-3 w-3" />
            {labelFor(model)}
            {datasetIds.length > 0 && (
              <span className="text-muted-foreground">· scoped</span>
            )}
          </span>
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={handleClear}
            className="ml-auto rounded-md px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
          >
            New chat
          </button>
        )}
      </header>

      {/* ChatMessages' StickToBottom is the scroller (keeps the stream pinned to the bottom). */}
      <div className="min-h-0 flex-1">
        <ChatMessages
          messages={messages}
          onRegenerate={handleRegenerate}
          onOpenCitation={handleOpenCitation}
          showThinking={showLoadingIndicator}
          onExamplePrompt={(text) => handleSubmit({ text, files: [] })}
        />
      </div>

      <div className="mx-auto w-full max-w-3xl shrink-0 px-4 pb-4">
        {/* Reusable hook guards this to ensure zero flashes */}
        {isStoreHydrated && needsClientKey && (
          <Alert variant="destructive" className="mb-2 mt-4">
            <AlertDescription className="flex items-center justify-between">
              <span>
                No API key available for {currentProvider}. Pick a model the
                server has a key for, or add your own.
              </span>
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
            const { summary, trace } = splitErrorTrace(
              error.message ?? "Something went wrong."
            );
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
          datasetIds={datasetIds}
          onDatasetIdsChange={setDatasetIds}
        />
      </div>
    </div>
  );
}
