"use client";

import {
  MutationCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import * as React from "react";

import { TickerCommandProvider } from "@/components/ticker-command";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(() => {
    const qc: QueryClient = new QueryClient({
      // Any action can change the credit count (starting an analysis spends one, a
      // failed run gives it back), so every successful one refreshes the counter
      // rather than each call site having to remember to.
      mutationCache: new MutationCache({
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: ["usage"] });
        },
      }),
      defaultOptions: {
        queries: {
          staleTime: 30_000,
          retry: 1,
          refetchOnWindowFocus: false,
        },
      },
    });
    return qc;
  });

  return (
    <QueryClientProvider client={client}>
      {/* defaultTheme="light" (the report card is designed on cream) and no transition on change: a theme switch that
          animates every colour on the page is a 300ms smear, not a transition. */}
      <ThemeProvider
        attribute="class"
        defaultTheme="light"
        enableSystem
        disableTransitionOnChange
      >
        <TooltipProvider delayDuration={150}>
          <TickerCommandProvider>
            {children}
            <Toaster position="bottom-right" />
          </TickerCommandProvider>
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
