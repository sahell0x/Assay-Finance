"use client";

import { Plus } from "lucide-react";
import { Accordion as A } from "radix-ui";

import { Appear, RiseText } from "@/components/landing/motion";
import { CONTAINER } from "@/components/landing/shared";
import { THRESHOLDS } from "@/components/scorecard-rail";

const QUESTIONS = [
  {
    q: "Is this financial advice?",
    a: "No. Assay tells you what a company's own numbers say and shows its working, so you can make up your own mind. It does not know your situation, and it is not a recommendation to buy or sell anything.",
  },
  {
    q: "Where do the numbers come from?",
    a: "From the annual and quarterly reports companies file with the US regulator, plus the current share price. The write-up also reads recent filings and news, and every claim in it links to the one it came from.",
  },
  {
    q: "How is buy, hold or sell decided?",
    a: `Five areas are scored out of 10 and weighted into one overall score. ${THRESHOLDS.buy} or above is a buy, ${THRESHOLDS.hold} up to ${THRESHOLDS.buy} is a hold, and below ${THRESHOLDS.hold} is a sell. The rules are the same for every company, and no one adjusts them by hand.`,
  },
  {
    q: "Which companies can I look up?",
    a: "Most companies listed on a US stock exchange. If a company has not published enough years of reports, the report says which parts it could not score instead of guessing.",
  },
  {
    q: "How long does a report take?",
    a: "Usually about two minutes. You can watch each step while it runs, and a company someone has already analyzed recently opens straight away.",
  },
  {
    q: "What does a credit pay for?",
    a: "One credit runs one new report. You get three without an account and ten more, once, when you sign up. Opening a report that already exists is always free.",
  },
];

/** The questions a first-time visitor actually has, answered in plain English. */
export function Faq() {
  return (
    <section aria-labelledby="faq-heading" className="border-t border-rule py-24 sm:py-32">
      <div className={`${CONTAINER} grid gap-12 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:gap-20`}>
        <div>
          <h2
            id="faq-heading"
            className="text-[36px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-[52px]"
          >
            <RiseText inView text="Questions, answered." />
          </h2>
          <Appear delay={0.15}>
            <p className="mt-5 text-[17px] leading-relaxed text-ink-muted">
              Anything else is covered on{" "}
              <a href="/how-it-works" className="font-semibold text-ink underline underline-offset-4">
                how it works
              </a>
              .
            </p>
          </Appear>
        </div>

        <Appear delay={0.1}>
          <A.Root type="single" collapsible defaultValue="0" className="border-t border-rule">
            {QUESTIONS.map(({ q, a }, i) => (
              <A.Item key={q} value={String(i)} className="border-b border-rule">
                <A.Header>
                  <A.Trigger className="group flex w-full items-center justify-between gap-6 py-6 text-left text-[18px] font-semibold tracking-[-0.015em] text-ink outline-none focus-visible:underline sm:text-[20px]">
                    {q}
                    <span className="grid size-8 shrink-0 place-items-center rounded-full border border-rule transition-[transform,background-color,color] duration-300 group-hover:border-brand-edge group-data-[state=open]:rotate-45 group-data-[state=open]:bg-ink group-data-[state=open]:text-paper">
                      <Plus className="size-4" aria-hidden />
                    </span>
                  </A.Trigger>
                </A.Header>
                <A.Content className="overflow-hidden data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down">
                  <p className="max-w-[62ch] pb-6 text-[16px] leading-relaxed text-ink-muted">{a}</p>
                </A.Content>
              </A.Item>
            ))}
          </A.Root>
        </Appear>
      </div>
    </section>
  );
}
