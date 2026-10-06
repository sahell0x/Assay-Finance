import type { Metadata } from "next";

import { CreditsClient } from "@/components/pages/credits-client";

export const metadata: Metadata = { title: "Credits" };

export default function CreditsPage() {
  return <CreditsClient />;
}
