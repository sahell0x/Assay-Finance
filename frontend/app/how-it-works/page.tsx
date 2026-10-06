import type { Metadata } from "next";
import Link from "next/link";

import { PageShell } from "@/components/page-shell";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "Where the numbers come from, how the buy, hold or sell rating is decided, and what a credit is.",
};

/** Written for the person using the product, not for the person who built it. The
 *  engineering write-up that used to live here is kept in docs/. */
const STEPS = [
  {
    title: "We read the official reports",
    body: "Every US-listed company publishes financial reports every quarter and every year. We take the numbers straight from those, along with today's share price.",
  },
  {
    title: "We do the math",
    body: "Around forty measures are calculated from those numbers: how profitable the company is, how much debt it carries, how fast it is growing and how expensive its shares are. Each one shows exactly how it was worked out.",
  },
  {
    title: "We compare it with similar companies",
    body: "A 30% profit margin can be excellent in one industry and ordinary in another, so each measure is ranked against a group of similar companies.",
  },
  {
    title: "We score it",
    body: "The measures are combined into a score out of 10, using the same fixed rules for every company. The score sets the rating: below 5 is a sell, 5 to 7.5 is a hold, above 7.5 is a buy.",
  },
  {
    title: "We explain it",
    body: "Finally we read recent reports and news and write a plain-English summary of why the company scored the way it did. Every number in it is checked against our calculations, and every claim links to its source.",
  },
];

const FAQ = [
  {
    q: "Is this investment advice?",
    a: "No. It is information to help you understand a company. It does not know your circumstances, and it can be wrong. Please do your own research, and speak to a qualified adviser before making investment decisions.",
  },
  {
    q: "What do buy, hold and sell mean here?",
    a: "They describe the score, nothing more. Buy means the company scored above 7.5 out of 10 on our rules, hold means between 5 and 7.5, and sell means below 5. They are not a prediction of where the share price will go.",
  },
  {
    q: "What is the fair value range?",
    a: "An estimate of what one share would be worth if the market valued this company the way it values similar companies. If today's price is well above the range, the shares look expensive compared with their peers; well below, they look cheap. It is not available when there is not enough data on similar companies.",
  },
  {
    q: "What is a credit?",
    a: "Each new analysis uses one credit. Without an account you get 3 free credits. A free account adds 10 more, once. After that you can buy small packs (payments run in test mode, so no real money is charged). Opening a company that was analyzed recently is free and instant, and an analysis that fails does not use a credit.",
  },
  {
    q: "Why could a company not be analyzed?",
    a: "Usually because it does not publish the financial reports we need. That includes funds, indexes, very new listings and some foreign companies. If you typed a company name, try its ticker symbol instead, for example AAPL for Apple.",
  },
  {
    q: "How up to date is it?",
    a: "Share prices are taken when the analysis runs. Financial reports come out every three months, so the underlying numbers change quarterly. The date on each analysis shows when it was made, and you can always run a fresh one.",
  },
  {
    q: "Can the written summary make things up?",
    a: "We work hard to stop it. The summary is never allowed to invent a number: every figure is checked against our calculations before you see it. Any claim about the business that cannot be linked to a source is removed. The numbers in brackets, like [1], take you to the exact passage it came from.",
  },
  {
    q: "What does the “What if?” tab do?",
    a: "It lets you change any number, for example the share price or the growth rate, and see how the score and rating would change. Nothing is saved and it does not use a credit.",
  },
];

export default function HowItWorksPage() {
  return (
    <PageShell
      eyebrow="How it works"
      title="How it works"
      lede="Pick a company and in about two minutes you get a score out of 10, a buy, hold or sell rating, and a plain-English explanation — every part of which you can check."
    >
      <section className="mb-14">
        <h2 className="mb-6 text-section">What happens when you analyze a company</h2>
        <ol className="grid gap-x-10 gap-y-8 md:grid-cols-2 lg:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="border-t-2 border-rule pt-4">
              <span className="nums text-small font-medium text-primary">Step {i + 1}</span>
              <h3 className="mt-1 text-lead font-medium text-ink">{s.title}</h3>
              <p className="mt-2 text-base leading-relaxed text-muted-foreground">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mb-14">
        <h2 className="mb-6 text-section">Common questions</h2>
        <div className="grid gap-x-12 gap-y-9 lg:grid-cols-2">
          {FAQ.map((d) => (
            <article key={d.q}>
              <h3 className="text-lead font-medium text-ink">{d.q}</h3>
              <p className="mt-2 text-base leading-relaxed text-muted-foreground">{d.a}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-t border-rule pt-8">
        <p className="text-base text-muted-foreground">
          Ready to try it?{" "}
          <Link href="/analyze" className="text-primary hover:underline">
            Analyze a company
          </Link>
          .
        </p>
      </section>
    </PageShell>
  );
}
