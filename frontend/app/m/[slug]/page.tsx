import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { inShort } from "@/components/in-short";
import { MemoView } from "@/components/memo-view";
import { TearSheet } from "@/components/tear-sheet";
import { SERVER_API_URL } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AnalysisDetail } from "@/lib/types";

async function getMemo(slug: string): Promise<AnalysisDetail | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/public/${slug}`, { next: { revalidate: 120 } });
    if (!res.ok) return null;
    return (await res.json()) as AnalysisDetail;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const memo = await getMemo(slug);
  if (!memo) return { title: "Analysis not found" };
  const name = memo.blocks?.market?.name;
  const company = name ? `${name} (${memo.ticker})` : memo.ticker;
  const rating = memo.scorecard?.rating;
  const word = rating ? rating[0] + rating.slice(1).toLowerCase() : null;
  const description = inShort(memo) ?? undefined;
  return {
    title: word ? `${company}: ${word}` : company,
    description,
    openGraph: { title: word ? `${company}: ${word}` : company, description, type: "article" },
  };
}

/** A shared memo. Public, read-only, and complete — the whole point of sharing one is
 *  that the recipient can check the sources. */
export default async function PublicMemoPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const analysis = await getMemo(slug);
  if (!analysis) notFound();

  return (
    <>
      <TearSheet analysis={analysis} />
      <div className="mx-auto max-w-[78rem] px-4 py-8 sm:px-6">
        <p className="mb-7 max-w-[62ch] text-small text-muted-foreground">
          A shared analysis from{" "}
          {formatDate(analysis.completed_at ?? analysis.created_at)}. Every number comes
          from the company&rsquo;s official financial reports, and the rating follows the
          same fixed rules for every company. The sources behind each claim are listed
          at the end.
        </p>

        <MemoView analysis={analysis} compact />

        {analysis.evidence.length > 0 && (
          <section className="mt-12 border-t border-rule pt-8">
            <h2 className="mb-4 text-section">Sources</h2>
            <ol className="space-y-3">
              {analysis.evidence.map((e) => (
                <li key={e.label} id={`source-${e.label}`} className="panel p-4">
                  <div className="mb-1.5 flex flex-wrap items-baseline gap-x-3">
                    <span className="nums text-small font-medium text-primary">
                      [{e.label.slice(1)}]
                    </span>
                    <span className="text-small text-ink">
                      {e.section ?? e.source_type}
                    </span>
                    {e.published && (
                      <span className="nums text-micro text-muted-foreground">
                        {formatDate(e.published)}
                      </span>
                    )}
                  </div>
                  <p className="memo-prose max-w-none text-base" style={{ lineHeight: 1.65 }}>
                    {e.text}
                  </p>
                  {e.url && (
                    <a
                      href={e.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="mt-2 inline-block text-micro text-primary hover:underline"
                    >
                      {e.title ?? "Open the source document"}
                    </a>
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
    </>
  );
}
