"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

/** Follow or stop following a company.
 *
 *  No account required: the watchlist is scoped to whoever is asking, and for a visitor
 *  without one that is their cookie. The toast says where the list lives rather than
 *  making the promise silently.
 */
export function WatchButton({ ticker }: { ticker: string }) {
  const queryClient = useQueryClient();
  const router = useRouter();

  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: api.watchlist,
    staleTime: 30_000,
  });

  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
    staleTime: 60_000,
  });

  const watching = watchlist.some((w) => w.ticker === ticker);

  const toggle = useMutation({
    mutationFn: async () => {
      if (watching) await api.removeWatch(ticker);
      else await api.addWatch(ticker);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      toast.success(
        watching ? `${ticker} removed from your watchlist` : `${ticker} added to your watchlist`,
        watching
          ? undefined
          : {
              description: user
                ? undefined
                : "Saved in this browser. Create an account to keep it on any device.",
              action: {
                label: "Open watchlist",
                onClick: () => router.push("/watchlist"),
              },
            },
      );
    },
    onError: () => toast.error("That could not be saved. Try again in a moment."),
  });

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => toggle.mutate()}
      disabled={toggle.isPending}
      aria-pressed={watching}
    >
      <Star
        className={cn("size-3.5", watching && "fill-current text-hold")}
        strokeWidth={2}
      />
      {watching ? "On watchlist" : "Add to watchlist"}
    </Button>
  );
}
