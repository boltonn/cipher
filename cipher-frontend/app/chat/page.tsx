"use client";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useState } from "react";

export default function ChatPage() {
  const { keys, model } = useChatStore();
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
  const currentApiKey = keys[currentProvider];

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
      api: "http://localhost:8000/api/chat",
    }),
  });

  const isLoading = status === "submitted" || status === "streaming";

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
        },
      }
    );
  };

  const handleRegenerate = () => {
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

    setMessages(messages.slice(0, messages.length - lastUserIndex));
    sendMessage({ text });
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
        {isLoading && (
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

      {error && (
        <Alert variant="destructive" className="mb-2 mt-4">
          <AlertDescription className="flex items-center justify-between">
            <span>{error.message ?? "Something went wrong."}</span>
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
          </AlertDescription>
        </Alert>
      )}

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
      />
    </div>
  );
}
