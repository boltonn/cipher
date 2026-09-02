"use client";

import { Shimmer } from "@/components/ai-elements/shimmer";
import { Skeleton } from "@/components/ui/skeleton";
import { AssistantAvatar } from "./assistant-avatar";

/**
 * Shown while the assistant has accepted a turn but hasn't started streaming
 * text -- a message-shaped skeleton (real avatar + placeholder lines) so the
 * handoff to the streamed reply doesn't shift layout.
 */
export function ThinkingIndicator() {
  return (
    <div className="flex w-full items-start gap-3">
      <AssistantAvatar />
      <div className="flex min-w-0 flex-1 flex-col gap-2 pt-1">
        <Shimmer className="text-xs font-medium">Thinking…</Shimmer>
        <div className="flex flex-col gap-2">
          <Skeleton className="h-3 w-[62%]" />
          <Skeleton className="h-3 w-[90%] [animation-delay:120ms]" />
          <Skeleton className="h-3 w-[74%] [animation-delay:240ms]" />
        </div>
      </div>
    </div>
  );
}
