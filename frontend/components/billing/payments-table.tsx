"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { SkeletonTable } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatDateTime, formatRupees } from "@/lib/format";
import type { PaymentRecord } from "@/lib/types";

const STATUS: Record<
  PaymentRecord["status"],
  { label: string; tone: "buy" | "hold" | "sell" | "neutral"; help: string }
> = {
  paid: { label: "Paid", tone: "buy", help: "Credits added to your account." },
  pending: {
    label: "In progress",
    tone: "neutral",
    help: "The payment window was opened. If you paid, credits arrive within a few minutes.",
  },
  abandoned: {
    label: "Not completed",
    tone: "neutral",
    help: "The payment window was closed before paying. Nothing was charged.",
  },
  refunded: {
    label: "Refunded",
    tone: "hold",
    help: "Over the test-mode limit, so no credits were added and the payment was given back.",
  },
  over_limit: {
    label: "Refund due",
    tone: "sell",
    help: "Over the test-mode limit. No credits were added; the refund is being retried.",
  },
};

/** Receipts: every time the payment window was opened, and how it ended. */
export function PaymentsTable() {
  const { data, isLoading } = useQuery({ queryKey: ["payments"], queryFn: api.payments });
  const items = data?.items ?? [];

  return (
    <section aria-labelledby="payments-heading">
      <h2 id="payments-heading" className="mb-3 text-section">
        Payments
      </h2>
      {isLoading ? (
        <SkeletonTable rows={3} />
      ) : items.length === 0 ? (
        <p className="border-t border-rule py-6 text-base text-muted-foreground">
          No payments yet. Receipts for credits you buy will appear here.
        </p>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[40rem] text-base">
            <thead>
              <tr className="border-b border-rule text-left text-small text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">Date</th>
                <th className="px-4 py-2.5 font-medium">Pack</th>
                <th className="px-4 py-2.5 text-right font-medium">Amount</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Payment reference</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const s = STATUS[p.status];
                return (
                  <tr key={p.id} className="border-b border-rule-soft last:border-0">
                    <td className="whitespace-nowrap px-4 py-2.5 text-small text-muted-foreground">
                      {formatDateTime(p.paid_at ?? p.created_at)}
                    </td>
                    <td className="px-4 py-2.5 text-ink">
                      {p.pack_name}{" "}
                      <span className="text-small text-muted-foreground">
                        · {p.credits} credits
                      </span>
                    </td>
                    <td className="nums whitespace-nowrap px-4 py-2.5 text-right text-ink">
                      {formatRupees(p.amount_paise)}
                    </td>
                    <td className="px-4 py-2.5" title={s.help}>
                      <Badge tone={s.tone}>{s.label}</Badge>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-micro text-muted-foreground">
                      {p.payment_id ?? p.order_id ?? ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {data?.test_mode && items.length > 0 && (
        <p className="mt-2 text-micro text-muted-foreground">
          These are Razorpay test-mode payments. No real money was charged.
        </p>
      )}
    </section>
  );
}
