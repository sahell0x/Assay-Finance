import type { Metadata } from "next";

import { HistoryClient } from "@/components/pages/history-client";

export const metadata: Metadata = { title: "History" };

export default function HistoryPage() {
  return <HistoryClient />;
}
