import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { inShort } from "@/components/in-short";
import { SERVER_API_URL } from "@/lib/api";
import type { AnalysisDetail } from "@/lib/types";

import { AnalysisClient } from "./client";

/** A real title for the tab and for a pasted link: "The Coca-Cola Company (KO): Hold"
 *  says what the page is, where "Analysis" said nothing. */
/** The analysis, or null. `notFound` for ids that do not exist (404) or cannot exist
 *  (422, not a UUID); anything else (API down) still renders and lets the client retry. */
async function fetchAnalysis(
  id: string,
): Promise<AnalysisDetail | "missing" | null> {
  try {
    const res = await fetch(
      `${SERVER_API_URL}/analyses/${encodeURIComponent(id)}`,
      {
        // Not cached: a run that is still going has no company name or rating yet, and
      // a cached copy kept the tab reading "PEP" after it had finished.
      cache: "no-store",
      },
    );
    if (res.status === 404 || res.status === 422) return "missing";
    if (!res.ok) return null;
    return (await res.json()) as AnalysisDetail;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const a = await fetchAnalysis(id);
  if (a === "missing") return { title: "Page not found" };
  if (!a) return { title: "Analysis" };
  const name = a.blocks?.market?.name;
  const company = name ? `${name} (${a.ticker})` : a.ticker;
  const rating = a.scorecard?.rating;
  const word = rating ? rating[0] + rating.slice(1).toLowerCase() : null;
  return {
    title: word ? `${company}: ${word}` : company,
    description: inShort(a) ?? undefined,
  };
}

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if ((await fetchAnalysis(id)) === "missing") notFound();
  return <AnalysisClient id={id} />;
}
