"use client";

import { StatusPage, statusKindFor } from "@/components/status-page";
import { apiErrorCode } from "@/lib/api-errors";
import { useEffect } from "react";

/**
 * Catches anything else a page in the app group throws (not found / forbidden / unauthorized
 * reads go to `not-found.tsx` / `forbidden.tsx` / `unauthorized.tsx` instead) and shows the
 * matching status page. Unexpected errors are logged for developers, never shown.
 */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const code = apiErrorCode(error);

  useEffect(() => {
    if (!code) console.error("[app] render error", error);
  }, [code, error]);

  return <StatusPage kind={statusKindFor(code)} onRetry={reset} />;
}
