"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { AnalysisResult } from "@/components/analysis-result";
import { EmptyPanel } from "@/components/app/kit";
import { RunView } from "@/components/app/run-view";
import { EASE } from "@/components/landing/motion";
import { QuotaGate } from "@/components/quota-gate";
import { WatchButton } from "@/components/watch-button";
import { Button } from "@/components/ui/button";
import { SkeletonTable } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { useAnalysisStream } from "@/lib/use-analysis-stream";

/** The result page.
 *
 *  While a run is in flight this shows the pipeline; once it finishes it swaps to the
 *  tabs. A cached result still plays its recorded pipeline first, badged honestly, with
 *  a control to compute a fresh one instead — the pipeline is the most informative thing
 *  in the interface and a cache hit should not throw it away.
 */
export function AnalysisClient({ id }: { id: string }) {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => api.getAnalysis(id),
    refetchInterval: (q) =>
      q.state.data && ["queued", "running"].includes(q.state.data.status) ? 4000 : false,
  });

  const live = useAnalysisStream(
    id,
    Boolean(data && ["queued", "running", "complete"].includes(data.status)),
  );

  // "Has the replay finished" is derived, not stored: it is true once the stream reports
  // a terminal status, or as soon as the reader asks to skip. Storing it and setting it
  // from an effect produced a cascading render on every status change.
  const [skipped, setSkipped] = React.useState(false);
  const streamFinished = live.status === "complete" || live.status === "failed";
  const replayDone = skipped || streamFinished;

  React.useEffect(() => {
    if (!streamFinished) return;
    queryClient.invalidateQueries({ queryKey: ["analysis", id] });
    queryClient.invalidateQueries({ queryKey: ["usage"] });
  }, [streamFinished, id, queryClient]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[78rem] px-4 py-10 sm:px-6">
        <SkeletonTable rows={6} />
      </div>
    );
  }

  if (error || !data) {
    const message =
      error instanceof ApiError ? error.message : "That analysis could not be loaded.";
    return (
      <EmptyState
        title="Analysis not found"
        body={message}
        action={<Button asChild variant="default"><Link href="/analyze">Run a new analysis</Link></Button>}
      />
    );
  }

  if (data.status === "failed") {
    return (
      <EmptyState
        title={`${data.ticker} could not be analyzed`}
        body={
          data.error ??
          "This analysis stopped before it finished. Your credit was not used."
        }
        action={
          <div className="flex gap-2">
            <Button asChild variant="default">
              <Link href="/analyze">Analyze a company</Link>
            </Button>
          </div>
        }
      />
    );
  }

  const running = data.status === "queued" || data.status === "running";
  const showPipeline = running || (data.cached && !replayDone);

  if (showPipeline) {
    return (
      <RunView
        ticker={data.ticker}
        name={data.blocks?.market?.name}
        startedAt={data.created_at}
        intro={
          data.cached
            ? "This company was analyzed recently, so you get the saved result for free. Here is how it ran."
            : "Reading the financial reports, doing the math and checking the news. This takes about two minutes, and you can leave this page and find it later in History."
        }
        actions={
          data.cached ? (
            <>
              <Button variant="ghost" size="sm" onClick={() => setSkipped(true)}>
                Skip to the result
              </Button>
              <RunLiveButton ticker={data.ticker} />
            </>
          ) : undefined
        }
        pipeline={live.pipeline.length ? live.pipeline : data.pipeline}
        nodes={live.nodes}
        currentNode={live.currentNode}
        status={live.status}
        replaying={live.replaying}
      />
    );
  }

  return (
    // The report settles in as the run screen leaves, rather than snapping into place.
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE }}
    >
      {data.cached && <CachedBanner ticker={data.ticker} at={data.cached_at} />}
      <QuotaGate />
      <AnalysisResult
        analysis={data}
        actions={
          <>
            <WatchButton ticker={data.ticker} />
            {/* The server only hands the PDF to the owner, or to anyone once it has been
                shared publicly; offering it to other viewers produced a raw error. */}
            {(data.owned || data.public_slug) && (
              <Button asChild variant="outline" size="sm">
                <a href={api.pdfUrl(data.id)} download>
                  Download PDF
                </a>
              </Button>
            )}
            <RunLiveButton ticker={data.ticker} />
          </>
        }
      />
    </motion.div>
  );
}

function CachedBanner({ ticker, at }: { ticker: string; at?: string | null }) {
  return (
    <div className="border-b border-rule bg-surface">
      <div className="mx-auto flex max-w-[78rem] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 sm:px-6">
        <p className="text-small text-ink-soft">
          This is a saved analysis
          {at ? ` from ${new Date(at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}` : ""}
          , so it was free. Company reports only change every three months, so a fresh one
          would usually give the same answer.
        </p>
        <div className="ml-auto">
          <RunLiveButton ticker={ticker} />
        </div>
      </div>
    </div>
  );
}

function RunLiveButton({ ticker }: { ticker: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [busy, setBusy] = React.useState(false);
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const res = await api.runAnalysis({ ticker, force_refresh: true });
          queryClient.invalidateQueries({ queryKey: ["usage"] });
          router.push(`/analysis/${res.id}`);
        } catch {
          setBusy(false);
        }
      }}
    >
      {busy ? "Starting" : "Get a fresh analysis (uses 1 credit)"}
    </Button>
  );
}

function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-[78rem] px-4 py-16 sm:px-6">
      <EmptyPanel title={title} body={body} action={action} />
    </div>
  );
}
