"use client";

import Link from "next/link";
import { useEffect } from "react";

import { PageShell } from "@/components/page-shell";
import { Button } from "@/components/ui/button";
import { reportError } from "@/lib/report-error";

/** Anything that throws while rendering a page lands here instead of a blank screen. */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
    reportError(error);
  }, [error]);

  return (
    <PageShell title="Something went wrong">
      <div className="border-t border-rule py-12">
        <p className="max-w-[52ch] text-lead leading-relaxed text-muted-foreground">
          This page could not be shown. Your analyses and credits are safe. Try again, and
          if it keeps happening, go back to the dashboard.
        </p>
        <div className="mt-7 flex gap-2">
          <Button onClick={() => reset()}>Try again</Button>
          <Button asChild variant="outline">
            <Link href="/dashboard">Go to the dashboard</Link>
          </Button>
        </div>
      </div>
    </PageShell>
  );
}
