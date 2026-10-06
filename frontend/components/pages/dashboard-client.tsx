"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Search } from "lucide-react";
import Link from "next/link";

import { AnalysisRows } from "@/components/analysis-rows";
import { EmptyPanel, StatTile } from "@/components/app/kit";
import { CreditsTile, ShowcaseRail, VerdictMixTile } from "@/components/app/dashboard-widgets";
import { WatchCard } from "@/components/app/watchlist-card";
import { AnonymousNotice, PageShell } from "@/components/page-shell";
import { TickerLauncher } from "@/components/ticker-launcher";
import { useTickerCommand } from "@/components/ticker-command";
import { Button } from "@/components/ui/button";
import { Skeleton, SkeletonTable } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { Rating } from "@/lib/types";

function SectionHead({ title, href, linkLabel }: { title: string; href?: string; linkLabel?: string }) {
  return (
    <div className="mb-4 flex items-baseline justify-between gap-4">
      <h2 className="text-[21px] font-semibold tracking-[-0.025em] text-ink">{title}</h2>
      {href && linkLabel && (
        <Link href={href} className="group inline-flex items-center gap-1 text-[14px] font-medium text-ink">
          {linkLabel}
          <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </Link>
      )}
    </div>
  );
}

/** Home after signing in: where your credits stand, how your verdicts split, the
 *  companies you follow drawn as their report shapes, and what ran most recently. An
 *  account with nothing finished yet gets graded companies to open for free instead of
 *  an empty table. */
export function DashboardClient() {
  const command = useTickerCommand();
  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });

  const { data: analyses = [], isLoading } = useQuery({
    queryKey: ["analyses", { limit: 50 }],
    queryFn: () => api.listAnalyses({ limit: 50 }),
  });

  const { data: watchlist = [], isLoading: watchLoading } = useQuery({
    queryKey: ["watchlist"],
    queryFn: api.watchlist,
  });

  const { data: usage } = useQuery({ queryKey: ["usage"], queryFn: api.usage });

  const finished = analyses.filter((a) => a.status === "complete" && a.rating);
  const ratings = finished.map((a) => a.rating as Rating);
  const name = user?.name?.split(" ")[0] ?? user?.email?.split("@")[0];

  return (
    <PageShell
      title="Dashboard"
      lede={
        name
          ? `Welcome back, ${name}. Here is where your companies stand.`
          : "Your credits, your watchlist and your latest analyses in one place."
      }
      action={<TickerLauncher />}
    >
      {!user && <AnonymousNotice what="This dashboard" />}

      {usage?.budget?.exhausted && (
        <p className="mb-6 rounded-[14px] border border-rule bg-hold-wash px-5 py-3.5 text-[14px] text-hold">
          New analyses are paused for today. Analyses already run still open normally.
        </p>
      )}

      <section aria-label="At a glance" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <CreditsTile usage={usage} />
        <StatTile
          label="Analyses finished"
          value={isLoading ? null : finished.length}
          hint={
            analyses.length > finished.length
              ? `${analyses.length - finished.length} more in progress or stopped.`
              : "Each one is saved, and re-opening it is free."
          }
        />
        <StatTile
          label="Companies watched"
          value={watchLoading ? null : watchlist.length}
          hint={
            <Link href="/watchlist" className="font-medium text-ink underline-offset-4 hover:underline">
              Manage your watchlist
            </Link>
          }
        />
        <VerdictMixTile ratings={ratings} />
      </section>

      <section className="mt-12">
        <SectionHead title="Your watchlist" href="/watchlist" linkLabel="Manage" />
        {watchLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-[13.5rem] rounded-[14px]" />
            ))}
          </div>
        ) : watchlist.length === 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-[14px] border border-dashed border-brand-edge bg-surface px-5 py-5">
            <p className="max-w-[56ch] text-[15px] text-ink-muted">
              Follow a company to keep its latest verdict here. Use &ldquo;Add to watchlist&rdquo;
              on any report, or add one on the watchlist page.
            </p>
            <Button asChild variant="outline">
              <Link href="/watchlist">Add a company</Link>
            </Button>
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {watchlist.slice(0, 8).map((w, i) => (
              <li key={w.ticker}>
                <WatchCard entry={w} delay={i * 0.06} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-12">
        <SectionHead
          title="Recent analyses"
          href={analyses.length > 0 ? "/history" : undefined}
          linkLabel="See all"
        />
        {isLoading ? (
          <SkeletonTable rows={4} />
        ) : analyses.length === 0 ? (
          <EmptyPanel
            title="Your first verdict is two minutes away"
            body="Search for any US company. We read its reports, do the maths and give you a clear buy, hold or sell view."
            action={
              <>
                <Button size="lg" onClick={command.open}>
                  <Search aria-hidden /> Find a company
                </Button>
                <Button asChild size="lg" variant="outline">
                  <Link href="/how-it-works">How it works</Link>
                </Button>
              </>
            }
          />
        ) : (
          <AnalysisRows rows={analyses.slice(0, 6)} />
        )}
      </section>

      {!isLoading && finished.length === 0 && <ShowcaseRail />}
    </PageShell>
  );
}
