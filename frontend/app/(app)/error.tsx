"use client";

import { Button } from "@/components/ui/button";
import { RotateCw, TriangleAlert } from "lucide-react";
import { useEffect } from "react";

/**
 * Catches any render-time exception thrown by a page in the app group, so a
 * broken screen shows a plain, branded message with a way forward instead of
 * the framework's stark default card. The underlying error is logged for
 * developers, never shown.
 */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[app] render error", error);
  }, [error]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
        <TriangleAlert className="h-5 w-5" />
      </div>
      <div>
        <p className="text-sm font-medium text-foreground">This screen ran into a problem</p>
        <p className="mt-1 max-w-sm text-xs text-muted-foreground">
          Something failed while rendering this page. It’s usually temporary —
          try again, or head back to where you were.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs" onClick={reset}>
          <RotateCw size={13} />
          Try again
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 text-xs text-muted-foreground"
          onClick={() => window.history.back()}
        >
          Go back
        </Button>
      </div>
    </div>
  );
}
