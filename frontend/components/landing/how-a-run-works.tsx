"use client";

import {
  ChartLine,
  FileText,
  Gauge,
  Newspaper,
  Quote,
  Scale,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useReducedMotion } from "motion/react";
import Link from "next/link";
import * as React from "react";

import { AssayMark } from "@/components/brand";
import { Appear, RiseText } from "@/components/landing/motion";
import { CONTAINER } from "@/components/landing/shared";
import { AnimatedBeam } from "@/components/ui/animated-beam";
import { cn } from "@/lib/cn";

const INPUTS: { Icon: LucideIcon; label: string }[] = [
  { Icon: FileText, label: "Annual reports" },
  { Icon: ChartLine, label: "Share price" },
  { Icon: Users, label: "Similar companies" },
  { Icon: Newspaper, label: "Recent news" },
];

const OUTPUTS: { Icon: LucideIcon; label: string }[] = [
  { Icon: Gauge, label: "Score out of 10" },
  { Icon: Scale, label: "Buy, hold or sell" },
  { Icon: Quote, label: "Write-up with sources" },
];

/** The steps are numbered because they genuinely are a sequence: the maths has to
 *  finish before the write-up knows what it is explaining. */
const STEPS = [
  {
    n: 1,
    title: "You pick a company",
    body: "We gather its latest official financial reports, its current share price and a group of similar companies to compare it with.",
  },
  {
    n: 2,
    title: "We do the math",
    body: "Around forty measures of profit, debt, growth and value are calculated straight from those reports, and each one shows exactly how it was worked out.",
  },
  {
    n: 3,
    title: "You get a clear answer",
    body: "The numbers decide a score out of 10 and a buy, hold or sell rating. Then recent filings and news explain why, and every claim is checked against its source.",
  },
] as const;

const Node = React.forwardRef<HTMLDivElement, { Icon: LucideIcon; label: string; align: "start" | "end" }>(
  function Node({ Icon, label, align }, ref) {
    return (
      <div
        className={cn(
          "flex items-center gap-3",
          align === "end" ? "flex-row-reverse text-right" : "",
        )}
      >
        <div
          ref={ref}
          className="z-10 grid size-11 shrink-0 place-items-center rounded-xl border border-rule bg-paper text-ink shadow-float sm:size-12"
        >
          <Icon className="size-5" strokeWidth={1.8} aria-hidden />
        </div>
        <span className="hidden text-[14px] font-medium text-ink sm:block">{label}</span>
      </div>
    );
  },
);

type BeamStyle = Omit<
  React.ComponentProps<typeof AnimatedBeam>,
  "containerRef" | "fromRef" | "toRef"
>;

/** One node and the beam that joins it to the hub. Each owns its own ref, and the beam's
 *  svg is positioned against the diagram, the nearest positioned ancestor. */
function Linked({
  Icon,
  label,
  side,
  container,
  hub,
  curvature,
  delay,
  beam,
}: {
  Icon: LucideIcon;
  label: string;
  side: "in" | "out";
  container: React.RefObject<HTMLDivElement | null>;
  hub: React.RefObject<HTMLDivElement | null>;
  curvature: number;
  delay: number;
  beam: BeamStyle;
}) {
  const node = React.useRef<HTMLDivElement>(null);
  return (
    <>
      <Node ref={node} Icon={Icon} label={label} align={side === "in" ? "end" : "start"} />
      <AnimatedBeam
        containerRef={container}
        fromRef={side === "in" ? node : hub}
        toRef={side === "in" ? hub : node}
        curvature={curvature}
        delay={delay}
        {...beam}
      />
    </>
  );
}

/** From filing to verdict, as a picture: what goes in on the left, the assay in the
 *  middle, what comes out on the right. The beams run in the order a real run works. */
export function HowARunWorks() {
  const reduced = useReducedMotion();
  const container = React.useRef<HTMLDivElement>(null);
  const hub = React.useRef<HTMLDivElement>(null);
  const beam: BeamStyle = {
    // currentColor, so the beams follow the theme through the svg's text colour.
    className: "text-ink",
    pathColor: "currentColor",
    pathOpacity: 0.12,
    pathWidth: 1.5,
    gradientStartColor: "currentColor",
    gradientStopColor: "currentColor",
    duration: 3.2,
    repeat: reduced ? 0 : Infinity,
  };

  return (
    <section aria-labelledby="how-heading" className="py-24 sm:py-32">
      <div className={CONTAINER}>
        <div className="mx-auto max-w-[44rem] text-center">
          <h2
            id="how-heading"
            className="text-[36px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-[52px]"
          >
            <RiseText inView text="From filing to verdict." />
          </h2>
          <Appear delay={0.15}>
            <p className="mt-5 text-[17px] leading-relaxed text-ink-muted sm:text-[18px]">
              Assay reads what a careful analyst would read, does the arithmetic in the open,
              and writes down only what it can point to.
            </p>
          </Appear>
        </div>

        <Appear delay={0.1}>
          <div
            ref={container}
            className="relative mx-auto mt-14 grid max-w-[60rem] grid-cols-[1fr_auto_1fr] items-center gap-x-6 rounded-[20px] border border-rule bg-surface sm:gap-x-20 lg:gap-x-28 px-5 py-10 sm:px-10 sm:py-14"
          >
            <div className="flex flex-col items-end gap-7">
              {INPUTS.map((n, i) => (
                <Linked
                  key={n.label}
                  {...n}
                  side="in"
                  container={container}
                  hub={hub}
                  curvature={(i - 1.5) * -28}
                  delay={i * 0.25}
                  beam={beam}
                />
              ))}
            </div>

            <div
              ref={hub}
              className="z-10 grid size-20 place-items-center rounded-[22px] border border-rule bg-paper shadow-lift sm:size-24"
            >
              <AssayMark className="size-11 sm:size-12" />
            </div>

            <div className="flex flex-col items-start gap-9">
              {OUTPUTS.map((n, i) => (
                <Linked
                  key={n.label}
                  {...n}
                  side="out"
                  container={container}
                  hub={hub}
                  curvature={(i - 1) * -30}
                  delay={1.2 + i * 0.25}
                  beam={beam}
                />
              ))}
            </div>

          </div>
        </Appear>

        <ol className="mt-16 grid gap-10 md:grid-cols-3 md:gap-8">
          {STEPS.map(({ n, title, body }, i) => (
            <li key={n}>
              <Appear delay={i * 0.1} className="border-t border-ink pt-6">
                <span className="nums text-[14px] font-semibold text-ink-muted">Step {n}</span>
                <h3 className="mt-2 text-[22px] font-semibold tracking-[-0.025em] text-ink">{title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">{body}</p>
              </Appear>
            </li>
          ))}
        </ol>

        <p className="mt-12 text-center text-[15px] text-ink-muted">
          The stages and data sources are written up in full on{" "}
          <Link href="/how-it-works" className="font-semibold text-ink underline underline-offset-4">
            how it works
          </Link>
          .
        </p>
      </div>
    </section>
  );
}
