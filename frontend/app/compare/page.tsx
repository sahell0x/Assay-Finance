import type { Metadata } from "next";

import { CompareClient } from "@/components/pages/compare-client";

export const metadata: Metadata = { title: "Compare" };

export default function ComparePage() {
  return <CompareClient />;
}
