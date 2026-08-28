"use client";

import { Shimmer } from "@/components/ai-elements/shimmer";
import { RingSpinner } from "@/components/ui/loader";
import { AssistantAvatar } from "./assistant-avatar";

/** Shown while the assistant has accepted a turn but hasn't started streaming text. */
export function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-3">
      <AssistantAvatar />
      <div className="flex items-center gap-2.5">
        <RingSpinner size={20} />
        <Shimmer className="text-sm">Thinking…</Shimmer>
      </div>
    </div>
  );
}
