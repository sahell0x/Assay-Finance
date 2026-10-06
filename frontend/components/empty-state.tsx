import Link from "next/link";

import { EmptyPanel } from "@/components/app/kit";
import { Button } from "@/components/ui/button";

/** An empty screen is an invitation to act, not a shrug. Every one names the next step.
 *
 *  Drawn as a blank report card whose rings draw themselves in, because that is exactly
 *  what an empty dashboard or watchlist is waiting to be filled with.
 */
export function EmptyState({
  title,
  body,
  actionLabel,
  actionHref,
}: {
  title: string;
  body: string;
  actionLabel?: string;
  actionHref?: string;
}) {
  return (
    <EmptyPanel
      title={title}
      body={body}
      action={
        actionLabel && actionHref ? (
          <Button asChild size="lg">
            <Link href={actionHref}>{actionLabel}</Link>
          </Button>
        ) : undefined
      }
    />
  );
}

/** Errors state what happened and what to do, in the interface's voice. */
export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-2xl bg-sell-wash px-5 py-4">
      <h2 className="text-lead font-semibold tracking-tight text-ink">
        That did not load
      </h2>
      <p className="mt-1.5 max-w-[54ch] text-base leading-relaxed text-muted-foreground">
        {message}
      </p>
    </div>
  );
}
