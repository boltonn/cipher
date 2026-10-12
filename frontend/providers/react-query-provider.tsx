"use client";

import {
  MutationCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { isPageInterrupt } from "@/lib/api-errors";

function makeQueryClient() {
  const queryClient: QueryClient = new QueryClient({
    // Any write may change a tag (and who set it); refresh the open "who tagged this" views.
    mutationCache: new MutationCache({
      onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tags"] }),
    }),
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        staleTime: 1000 * 60 * 5, // 5 minutes
        // A missing / forbidden / signed-out read won't fix itself: no retry, and throwing the
        // interrupt during render shows not-found.tsx / forbidden.tsx / unauthorized.tsx.
        retry: (failureCount, error) => failureCount < 1 && !isPageInterrupt(error),
        throwOnError: isPageInterrupt,
      },
    },
  });
  return queryClient;
}

let browserQueryClient: QueryClient | undefined;

function getQueryClient() {
  // Keep server requests isolated and preserve the browser cache across renders.
  if (typeof window === "undefined") return makeQueryClient();
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}

export function ReactQueryProvider({ children }: { children: React.ReactNode }) {
  const queryClient = getQueryClient();

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
