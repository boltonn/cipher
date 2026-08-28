"use client";

import { ConversationDownload } from "@/components/ai-elements/conversation";
import {
  PromptInput,
  PromptInputBody,
  PromptInputButton,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import type { ChatStatus, UIMessage } from "ai";
import { Trash2Icon } from "lucide-react";
import { useState } from "react";
import { ModelConfigPopover } from "./model-config-popover";

interface ChatInputProps {
  status: ChatStatus;
  messages: UIMessage[];
  datasetId?: string;
  onDatasetIdChange: (datasetId: string | undefined) => void;
  onSubmit: (message: PromptInputMessage) => void;
  onStop: () => void;
  onClear: () => void;
}

export function ChatInput({
  status,
  messages,
  datasetId,
  onDatasetIdChange,
  onSubmit,
  onStop,
  onClear,
}: ChatInputProps) {
  const [text, setText] = useState("");

  const handleSubmit = (message: PromptInputMessage) => {
    if (!message.text.trim()) return;
    onSubmit(message);
    setText("");
  };

  return (
    <PromptInput onSubmit={handleSubmit}>
      <PromptInputBody>
        <PromptInputTextarea
          value={text}
          placeholder="Ask something..."
          onChange={(e) => setText(e.currentTarget.value)}
        />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          <ModelConfigPopover />
          <DatasetSelect datasetId={datasetId} onChange={onDatasetIdChange} className="h-7 w-44" />
          {messages.length > 0 && (
            <ConversationDownload
              messages={messages}
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-xs text-muted-foreground"
            />
          )}
          {messages.length > 0 && (
            <PromptInputButton
              tooltip={{ content: "Clear chat" }}
              variant="ghost"
              type="button"
              onClick={onClear}
            >
              <Trash2Icon size={14} />
            </PromptInputButton>
          )}
        </PromptInputTools>
        <PromptInputSubmit
          status={status}
          disabled={!text.trim() && status !== "streaming"}
          onClick={status === "streaming" ? onStop : undefined}
        />
      </PromptInputFooter>
    </PromptInput>
  );
}
