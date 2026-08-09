"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * QueryProvider — app-wide React Query client.
 *
 * @tanstack/react-query was already a project dependency but had never been
 * wired up; every existing dashboard page used useState/useEffect + axios
 * directly. This establishes the provider so new modules (starting with
 * Trust Network) can use useQuery/useMutation instead.
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
            staleTime: 30_000,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
