"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/** The signup prompt.
 *
 *  Deliberately placed *after* a result has rendered, and only once the allowance is
 *  actually gone. Gating before output leaves a visitor with nothing to evaluate and
 *  nothing to sign up for. The copy states what happened and what an account adds; it
 *  does not oversell, and it says plainly that the work already done carries over.
 */
export function QuotaGate() {
  const { data } = useQuery({ queryKey: ["usage"], queryFn: api.usage, retry: false });
  const [dismissed, setDismissed] = React.useState(false);

  if (!data || data.authenticated || !data.exhausted || dismissed) return null;

  return (
    <div className="border-b border-rule bg-surface">
      <div className="mx-auto max-w-[78rem] px-4 py-5 sm:px-6">
        <div className="flex flex-wrap items-start gap-x-10 gap-y-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-section">
              That was your {data.limit === 3 ? "third" : `${data.limit}th`} free analysis
            </h2>
            <p className="mt-1.5 max-w-[58ch] text-base leading-relaxed text-muted-foreground">
              Everything you have already run stays available and moves into your account
              when you create one. An account also adds{" "}
              {data.signup_benefits
                .slice(0, 3)
                .map((b) => b.toLowerCase())
                .join(", ")}
              .
            </p>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Button asChild variant="default">
              <a href={api.googleAuthorizeUrl()}>Continue with Google</a>
            </Button>
            <Button asChild variant="outline">
              <Link href="/signup">Use an email address</Link>
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setDismissed(true)}>
              Not now
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
