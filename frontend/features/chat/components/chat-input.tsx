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
import { DatasetMultiSelectCombobox } from "@/features/datasets/components/dataset-multi-select-combobox";
import type { ChatStatus, UIMessage } from "ai";
import { Trash2Icon } from "lucide-react";
import { useState } from "react";
import { AutonomyToggle } from "./autonomy-toggle";
import { ModelConfigPopover } from "./model-config-popover";

interface ChatInputProps {
  status: ChatStatus;
  messages: UIMessage[];
  datasetIds: string[];
  onDatasetIdsChange: (datasetIds: string[]) => void;
  onSubmit: (message: PromptInputMessage) => void;
  onStop: () => void;
  onClear: () => void;
}

export function ChatInput({
  status,
  messages,
  datasetIds,
  onDatasetIdsChange,
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
          <AutonomyToggle />
          <DatasetMultiSelectCombobox
            compact
            value={datasetIds}
            onChange={onDatasetIdsChange}
            placeholder="All my datasets"
            className="w-44"
            triggerClassName="h-7"
          />
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
