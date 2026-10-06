import type { Metadata } from "next";

import { AnalyzeForm } from "@/components/analyze-form";
import { PageShell } from "@/components/page-shell";

export const metadata: Metadata = {
  title: "New analysis",
  description: "Pick a company and get a buy, hold or sell view with the reasons behind it.",
};

export default function AnalyzePage() {
  return (
    <PageShell
      eyebrow="New analysis"
      title="Run an analysis"
      lede="Pick a company and get a clear buy, hold or sell view, with the reasons and the numbers behind it. Only the company is required."
    >
      <AnalyzeForm />
    </PageShell>
  );
}
