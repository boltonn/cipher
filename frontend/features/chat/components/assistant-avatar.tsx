import { cn } from "@/lib/utils";
import { SparklesIcon } from "lucide-react";

/** Gradient glyph used for the assistant, mirroring the avatar treatment in the sidebar/settings. */
export function AssistantAvatar({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-primary to-purple-600 text-white",
        className
      )}
    >
      <SparklesIcon className="h-4 w-4" />
    </div>
  );
}
