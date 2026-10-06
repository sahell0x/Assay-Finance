"use client";

import { motion, useReducedMotion } from "motion/react";
import * as React from "react";

import { CashCycleBar } from "@/components/charts/ccc-bar";
import { DupontWaterfall } from "@/components/charts/dupont-waterfall";
import { Gauges, type Gauge } from "@/components/charts/gauges";
import { MarginTrend } from "@/components/charts/margin-trend";
import { RevenueGrowth } from "@/components/charts/revenue-growth";
import { EASE } from "@/components/landing/motion";
import { EvidenceList } from "@/components/evidence-list";
import { MemoView } from "@/components/memo-view";
import { ScenarioPanel } from "@/components/scenario-panel";
import { MetricTab } from "@/components/tabs/metric-tab";
import { PeersTab } from "@/components/tabs/peers-tab";
import { TearSheet } from "@/components/tear-sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { AnalysisDetail } from "@/lib/types";

const TABS = [
  { value: "memo", label: "Summary" },
  { value: "scenario", label: "What if?" },
  { value: "profitability", label: "Profitability" },
  { value: "liquidity", label: "Financial health" },
  { value: "growth", label: "Growth" },
  { value: "peers", label: "Peers" },
  { value: "evidence", label: "Sources" },
];

export function AnalysisResult({
  analysis,
  actions,
  embedded = false,
}: {
  analysis: AnalysisDetail;
  actions?: React.ReactNode;
  /** Shown inside another page (the landing showcase), which has its own <h1>. */
  embedded?: boolean;
}) {
  const [tab, setTab] = React.useState("memo");
  const tabId = React.useId();
  /* Scenario is arithmetic over a finished scorecard; without one there is nothing to
     vary, and the endpoint would answer 409. */
  const tabs = analysis.scorecard ? TABS : TABS.filter((t) => t.value !== "scenario");
  const [highlight, setHighlight] = React.useState<string | null>(null);

  const blocks = analysis.blocks ?? {};
  const profitability = blocks.profitability;
  const liquidity = blocks.liquidity;
  const growth = blocks.growth;

  /** A citation marker jumps to the Evidence tab and lights up the source. A citation
   *  you cannot follow is decoration. */
  const goToSource = React.useCallback((label: string) => {
    setTab("evidence");
    setHighlight(label);
    requestAnimationFrame(() => {
      document
        .getElementById(`source-${label}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, []);

  const marginTrend =
    (profitability?.extras?.margin_trend as Parameters<typeof MarginTrend>[0]["data"]) ?? [];
  const revenueTrend =
    (growth?.extras?.revenue_trend as Parameters<typeof RevenueGrowth>[0]["data"]) ?? [];
  const gauges = (liquidity?.extras?.gauges as Gauge[]) ?? [];
  const ccc = (liquidity?.extras?.ccc_components ?? {}) as {
    dso: number | null;
    dio: number | null;
    dpo: number | null;
    ccc: number | null;
  };

  return (
    <>
      <TearSheet analysis={analysis} actions={actions} embedded={embedded} />

      <div className="mx-auto max-w-[78rem] px-4 sm:px-6">
        <Tabs value={tab} onValueChange={setTab}>
          {/* The section bar stays under the site header while you read, so another
              section is always one click away. It scrolls sideways on a phone rather
              than wrapping into two rows. */}
          <div className="sticky top-16 z-30 -mx-4 mb-3 border-b border-rule bg-paper/90 px-4 py-2.5 backdrop-blur-md sm:-mx-6 sm:px-6">
            <TabsList
              aria-label="Analysis sections"
              className="thin-scroll h-auto w-fit max-w-full justify-start gap-1 overflow-x-auto rounded-none border-0 bg-transparent p-0 group-data-horizontal/tabs:h-auto"
            >
              {tabs.map((t) => (
                <TabsTrigger
                  key={t.value}
                  value={t.value}
                  className="relative h-9 flex-none rounded-lg border-0 px-3.5 text-[14px] font-medium text-ink-muted hover:text-ink data-active:bg-transparent data-active:text-ink data-active:shadow-none dark:data-active:border-transparent dark:data-active:bg-transparent"
                >
                  {/* One highlight that slides to the section you pick. */}
                  {tab === t.value && (
                    <motion.span
                      layoutId={`report-tab-${tabId}`}
                      aria-hidden
                      className="absolute inset-0 rounded-lg bg-surface-sunk"
                      transition={{ type: "spring", stiffness: 460, damping: 38 }}
                    />
                  )}
                  <span className="relative">{t.label}</span>
                </TabsTrigger>
              ))}
            </TabsList>
          </div>

          <TabsContent value="memo">
            <Fade>
            <MemoView analysis={analysis} onCite={goToSource} />
            </Fade>
          </TabsContent>

          <TabsContent value="scenario">
            <Fade>
            <ScenarioPanel analysisId={String(analysis.id)} />
            </Fade>
          </TabsContent>

          <TabsContent value="profitability">
            <Fade>
            <MetricTab
              block={profitability}
              emptyReason="The profitability stage did not produce a result for this company."
              charts={
                <div className="grid gap-5 xl:grid-cols-2">
                  <MarginTrend data={marginTrend} />
                  <DupontWaterfall
                    dupont={
                      profitability?.extras?.dupont as Parameters<
                        typeof DupontWaterfall
                      >[0]["dupont"]
                    }
                  />
                </div>
              }
            />
            </Fade>
          </TabsContent>

          <TabsContent value="liquidity">
            <Fade>
            <MetricTab
              block={liquidity}
              emptyReason="The liquidity stage did not produce a result for this company."
              charts={
                <div className="grid gap-5 xl:grid-cols-2">
                  {gauges.length > 0 && <Gauges gauges={gauges} />}
                  <CashCycleBar
                    dso={ccc.dso ?? null}
                    dio={ccc.dio ?? null}
                    dpo={ccc.dpo ?? null}
                    ccc={ccc.ccc ?? null}
                  />
                </div>
              }
            />
            </Fade>
          </TabsContent>

          <TabsContent value="growth">
            <Fade>
            <MetricTab
              block={growth}
              emptyReason="The growth stage did not produce a result for this company."
              charts={<RevenueGrowth data={revenueTrend} />}
            />
            </Fade>
          </TabsContent>

          <TabsContent value="peers">
            <Fade>
            <PeersTab block={blocks.peers} />
            </Fade>
          </TabsContent>

          <TabsContent value="evidence" id="evidence">
            <Fade>
            <EvidenceList evidence={analysis.evidence} highlight={highlight} />
            </Fade>
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
}

/** A section settles in when you switch to it, so the change of view is visible. */
function Fade({ children }: { children: React.ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}
