import type { Metadata } from "next";

import { EmptyState } from "@/components/empty-state";
import { PageShell } from "@/components/page-shell";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <PageShell title="Page not found">
      <EmptyState
        title="There is nothing at this address"
        body="The link may be mistyped, or the analysis it pointed to may have been deleted. Search for a company to start a new one."
        actionLabel="Analyze a company"
        actionHref="/analyze"
      />
    </PageShell>
  );
}
