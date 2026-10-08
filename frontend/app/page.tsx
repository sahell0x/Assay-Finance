import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { LandingAuthRedirect } from "@/components/landing/auth-redirect";
import { Capabilities } from "@/components/landing/capabilities";
import { ClosingCta } from "@/components/landing/closing-cta";
import { Faq } from "@/components/landing/faq";
import { Grading } from "@/components/landing/grading";
import { Hero } from "@/components/landing/hero";
import { HowARunWorks } from "@/components/landing/how-a-run-works";
import { Insights } from "@/components/landing/insights";
import { SmoothScroll } from "@/components/landing/motion";
import { ShowcaseUnavailable } from "@/components/landing/showcase-unavailable";
import { Stage } from "@/components/landing/stage";
import { TickerTape } from "@/components/landing/ticker-tape";
import { fetchAnalysis, fetchShowcase } from "@/lib/api";

/** The landing page.
 *
 *  Written for somebody who has never read a 10-K. It opens on a real report being
 *  worked out, runs a tape of companies already graded, then shows what went into one
 *  report, what the grade is made of, a tour of a real run, the parts of a report you
 *  can open up and check, and how a run gets from filing to verdict.
 *
 *  Every animated figure on the page is read from stored analyses, fetched here rather
 *  than in the browser so the first company is in the HTML: the page's whole argument
 *  is that this is real output, and a spinner where the output should be undermines it.
 */
export const revalidate = 300;

export default async function LandingPage() {
  const cookieStore = await cookies();
  const sessionToken = cookieStore.get("era_session")?.value?.trim();
  if (sessionToken && sessionToken !== "deleted") {
    redirect("/dashboard");
  }

  const cards = await fetchShowcase(8);
  const first = cards[0] ? await fetchAnalysis(cards[0].id) : null;

  return (
    <>
      <LandingAuthRedirect />
      <SmoothScroll />
      <Hero cards={cards} />
      <TickerTape cards={cards} />
      {first && <Insights analysis={first} />}
      <Grading example={cards[0] ?? null} />
      {cards.length > 0 ? (
        <Stage cards={cards} initialAnalysis={first} />
      ) : (
        <ShowcaseUnavailable />
      )}
      <Capabilities analysis={first} cards={cards} />
      <HowARunWorks />
      <Faq />
      <ClosingCta />
    </>
  );
}
