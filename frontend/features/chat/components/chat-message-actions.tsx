"use client";

import {
  MessageAction,
  MessageActions,
} from "@/components/ai-elements/message";
import { CopyIcon, RefreshCcwIcon } from "lucide-react";

interface ChatMessageActionsProps {
  text: string;
  onRegenerate: () => void;
}

export function ChatMessageActions({
  text,
  onRegenerate,
}: ChatMessageActionsProps) {
  return (
    <MessageActions>
      <MessageAction onClick={onRegenerate} label="Retry">
        <RefreshCcwIcon className="size-3" />
      </MessageAction>
      <MessageAction
        onClick={() => navigator.clipboard.writeText(text)}
        label="Copy"
      >
        <CopyIcon className="size-3" />
      </MessageAction>
    </MessageActions>
  );
}
