"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, ShieldCheck } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { CountUp } from "@/components/app/kit";
import { ActivityLog } from "@/components/billing/activity-log";
import { PaymentsTable } from "@/components/billing/payments-table";
import { SpendTiles, UsageChart } from "@/components/billing/spend-summary";
import { EASE } from "@/components/landing/motion";
import { PageShell } from "@/components/page-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatRupees } from "@/lib/format";
import { openCheckout } from "@/lib/razorpay";
import type { CreditPack, TestLimits, UsageState } from "@/lib/types";

/** Buying credits.
 *
 *  The balance comes first because it answers the question most people arrive with
 *  ("how many do I have left?"), then the packs, then the history. Free credits are
 *  described before bought ones because they are spent first, and the page says so, so
 *  nobody is surprised that a pack they bought today is untouched at the end of the day.
 */
export function CreditsClient() {
  const queryClient = useQueryClient();
  const { data: user, isPending: userPending } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });
  const { data: usage } = useQuery({ queryKey: ["usage"], queryFn: api.usage, retry: false });
  const { data: shop, isLoading: shopLoading } = useQuery({
    queryKey: ["credit-packs"],
    queryFn: api.creditPacks,
    staleTime: 5 * 60_000,
  });
  const { data: summary } = useQuery({
    queryKey: ["billing-summary"],
    queryFn: api.billingSummary,
    enabled: Boolean(user),
    retry: false,
  });

  const [buying, setBuying] = React.useState<string | null>(null);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["usage"] });
    for (const key of ["credit-packs", "credit-activity", "billing-summary", "payments"]) {
      queryClient.invalidateQueries({ queryKey: [key] });
    }
  };

  const buy = useMutation({
    mutationFn: async (pack: CreditPack) => {
      const order = await api.createCreditOrder(pack.id);
      const result = await openCheckout(order);
      if (result.status !== "paid") return result;
      const confirmed = await api.confirmPayment(result.confirmation);
      return { status: "paid" as const, ...confirmed };
    },
    onMutate: (pack) => setBuying(pack.id),
    onSettled: () => setBuying(null),
    onSuccess: (result) => {
      if (result.status === "paid") {
        refresh();
        toast.success(`${result.credits_added} credits added`, {
          description: `You now have ${result.paid_credits} bought credits. They never expire.`,
        });
      } else if (result.status === "failed") {
        toast.error("The payment did not go through", {
          description: `${result.message} No money was taken. You can try again.`,
        });
      }
      // Dismissed without paying: nothing to say.
    },
    onError: (e) => {
      // A payment that Razorpay took but we could not confirm here is still granted by
      // the webhook, so the balance is refreshed in case it has already arrived.
      refresh();
      if (e instanceof ApiError && e.code === "test_limit_reached") {
        toast.error("Test-mode limit reached", { description: e.message });
        return;
      }
      toast.error(
        e instanceof ApiError ? e.message : "Something went wrong starting the payment.",
      );
    },
  });

  const signedOut = !userPending && !user;
  const limits = shop?.limits ?? null;
  const limitReached = Boolean(
    limits && (limits.purchases_left === 0 || limits.credits_left === 0),
  );

  return (
    <PageShell
      title="Credits"
      lede="Each new analysis uses 1 credit. The free credits that come with your account are used first, then any you buy. None of them expire."
    >
      {usage?.authenticated && <Balance usage={usage} />}

      {signedOut && (
        <div className="panel mb-8 flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <h2 className="text-section">Sign in to buy credits</h2>
            <p className="mt-1 max-w-[56ch] text-base leading-relaxed text-muted-foreground">
              Credits belong to your account, so they are there on any device. A free
              account also comes with {usage?.account_free_credits ?? 10} free credits to
              start.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild>
              <Link href="/signup">Create a free account</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/login">Sign in</Link>
            </Button>
          </div>
        </div>
      )}

      <section aria-labelledby="packs-heading" className="mb-12">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="packs-heading" className="text-[22px] font-semibold tracking-[-0.03em] text-ink">
            Buy more credits
          </h2>
          <p className="flex items-center gap-1.5 text-small text-muted-foreground">
            <ShieldCheck className="size-3.5" aria-hidden />
            Paid securely through Razorpay. Cards, UPI and netbanking.
          </p>
        </div>

        {shop?.test_mode && <TestModeNotice limits={limits} reached={limitReached} />}

        {shop && !shop.enabled && (
          <p className="mb-4 rounded-xl bg-surface-sunk px-4 py-3 text-base text-ink-soft">
            Buying credits is not available yet. Your free credits work as usual.
          </p>
        )}

        {shopLoading ? (
          <div className="grid gap-4 md:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-60 rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {shop?.packs.map((pack, i) => (
              <PackCard
                index={i}
                key={pack.id}
                pack={pack}
                cheapestPerCredit={Math.max(...shop.packs.map((p) => p.per_credit_paise))}
                disabled={!shop.enabled || !user || buy.isPending}
                blocked={
                  !limits
                    ? null
                    : limitReached
                      ? "Test limit reached"
                      : pack.credits > limits.credits_left
                        ? "Over the test limit"
                        : null
                }
                signedOut={signedOut}
                pending={buying === pack.id}
                onBuy={() => buy.mutate(pack)}
              />
            ))}
          </div>
        )}
      </section>

      {user && (
        <div className="space-y-10">
          {summary && (
            <section aria-labelledby="spending-heading" className="space-y-4">
              <h2 id="spending-heading" className="text-[22px] font-semibold tracking-[-0.03em] text-ink">
                Your spending
              </h2>
              <SpendTiles summary={summary} testMode={Boolean(shop?.test_mode)} />
              <UsageChart summary={summary} />
            </section>
          )}
          <ActivityLog />
          <PaymentsTable />
        </div>
      )}
    </PageShell>
  );
}

/** The balance, led by the one number people come for: how many analyses they can
 *  run now. The ring shows how much of the one-time free allowance is left. */
function Balance({ usage }: { usage: UsageState }) {
  const reduced = useReducedMotion();
  const r = 34;
  const C = 2 * Math.PI * r;
  const left = usage.limit > 0 ? usage.free_remaining / usage.limit : 0;

  return (
    <section className="mb-12 grid gap-px overflow-hidden rounded-[20px] border border-rule bg-rule lg:grid-cols-[1.3fr_1fr_1fr]">
      <div className="flex items-center gap-6 bg-surface p-6 sm:p-7">
        <svg viewBox="0 0 80 80" className="size-20 shrink-0 -rotate-90" aria-hidden>
          <circle cx="40" cy="40" r={r} fill="none" stroke="var(--surface-sunk)" strokeWidth="7" />
          <motion.circle
            cx="40"
            cy="40"
            r={r}
            fill="none"
            stroke="var(--ink)"
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={C}
            initial={reduced ? false : { strokeDashoffset: C }}
            animate={{ strokeDashoffset: C * (1 - left) }}
            transition={{ duration: 1.2, ease: EASE, delay: 0.2 }}
          />
        </svg>
        <div>
          <p className="text-[13px] font-medium text-ink-muted">Available now</p>
          <p className="mt-1.5 text-[44px] font-semibold leading-none tracking-[-0.045em] text-ink">
            <CountUp value={usage.remaining} />
          </p>
          <p className="mt-2 text-[13px] text-ink-muted">
            {usage.remaining === 1 ? "analysis you can run" : "analyses you can run"}
          </p>
        </div>
      </div>
      <Stat
        label="Free credits"
        value={usage.free_remaining}
        suffix={` of ${usage.limit} left`}
        note="Came with your account. One time, they do not reset."
      />
      <Stat
        label="Bought credits"
        value={usage.paid_credits}
        note="Used after your free credits. Never expire."
      />
    </section>
  );
}

function Stat({
  label,
  value,
  suffix,
  note,
}: {
  label: string;
  value: number;
  suffix?: string;
  note: string;
}) {
  return (
    <div className="flex flex-col bg-surface p-6 sm:p-7">
      <p className="text-[13px] font-medium text-ink-muted">{label}</p>
      <p className="mt-2 text-[28px] font-semibold leading-none tracking-[-0.035em] text-ink">
        <CountUp value={value} />
        {suffix && <span className="text-[15px] font-medium tracking-normal text-ink-muted">{suffix}</span>}
      </p>
      <p className="mt-auto pt-3 text-[13px] leading-relaxed text-ink-muted">{note}</p>
    </div>
  );
}

function PackCard({
  index,
  pack,
  cheapestPerCredit,
  disabled,
  blocked,
  signedOut,
  pending,
  onBuy,
}: {
  index: number;
  pack: CreditPack;
  cheapestPerCredit: number;
  disabled: boolean;
  /** Why this pack cannot be bought under the test-mode limit, if it cannot. */
  blocked: string | null;
  signedOut: boolean;
  pending: boolean;
  onBuy: () => void;
}) {
  const saving = Math.round((1 - pack.per_credit_paise / cheapestPerCredit) * 100);
  const reduced = useReducedMotion();
  const live = !disabled && !blocked;

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: EASE, delay: index * 0.08 }}
      whileHover={reduced || !live ? undefined : { y: -4 }}
      className={cn(
        "relative flex flex-col rounded-[20px] border bg-paper p-6 transition-shadow",
        pack.popular ? "border-ink shadow-lift" : "border-rule hover:shadow-float",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[15px] font-semibold text-ink">{pack.name}</h3>
        {pack.popular && (
          <span className="rounded-md bg-ink px-2 py-0.5 text-[12px] font-semibold text-paper">Most popular</span>
        )}
      </div>

      <div className="mt-4 flex items-baseline gap-1.5">
        <span className="nums text-[48px] font-semibold leading-none tracking-[-0.045em] text-ink">
          {pack.credits}
        </span>
        <span className="text-base text-muted-foreground">credits</span>
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span className="nums text-lead font-semibold text-ink">
          {formatRupees(pack.price_paise)}
        </span>
        <span className="nums text-small text-muted-foreground">
          {formatRupees(pack.per_credit_paise)} per analysis
        </span>
      </div>

      <ul className="mb-6 mt-5 space-y-2 text-[14px] text-ink-soft">
        <li className="flex gap-2">
          <Check className="mt-0.5 size-3.5 shrink-0 text-buy" aria-hidden />
          {pack.credits} new analyses
        </li>
        <li className="flex gap-2">
          <Check className="mt-0.5 size-3.5 shrink-0 text-buy" aria-hidden />
          Never expire
        </li>
        {saving > 0 && (
          <li className="flex gap-2">
            <Check className="mt-0.5 size-3.5 shrink-0 text-buy" aria-hidden />
            {saving}% cheaper per analysis than the smallest pack
          </li>
        )}
      </ul>

      <Button
        className="mt-auto w-full"
        size="lg"
        variant={pack.popular ? "default" : "outline"}
        disabled={disabled || Boolean(blocked)}
        onClick={onBuy}
      >
        {pending && <Loader2 className="size-4 animate-spin" aria-hidden />}
        {pending
          ? "Opening payment…"
          : blocked
            ? blocked
            : signedOut
            ? "Sign in to buy"
            : `Buy for ${formatRupees(pack.price_paise)}`}
      </Button>
    </motion.div>
  );
}

/** Said plainly and first: this shop is real, the money is not.
 *
 *  Someone trying the site should know before they click that nothing will be charged,
 *  what to type into the payment form, and how much they can buy.
 */
function TestModeNotice({
  limits,
  reached,
}: {
  limits: TestLimits | null;
  reached: boolean;
}) {
  return (
    <div className="mb-6 rounded-[14px] border border-hold/30 bg-hold-wash p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="hold">TEST MODE</Badge>
        <h3 className="text-base font-semibold text-ink">No real money is charged here</h3>
      </div>
      <p className="mt-2 max-w-[70ch] text-base leading-relaxed text-ink-soft">
        This is a portfolio project. Buying credits goes through Razorpay&rsquo;s real
        checkout, running in test mode, so you can try the whole flow without paying
        anything. Please do not enter your real card details.
      </p>
      <dl className="mt-3 grid gap-x-8 gap-y-1.5 text-small text-ink-soft sm:grid-cols-[auto_1fr]">
        <dt className="font-medium text-ink">Test card</dt>
        <dd className="nums">
          4111 1111 1111 1111, any future expiry date, any CVV. If a bank page opens,
          choose Success.
        </dd>
        <dt className="font-medium text-ink">Test UPI</dt>
        <dd className="nums">success@razorpay</dd>
      </dl>
      {limits && (
        <p className="mt-3 text-small text-ink-soft">
          {reached ? (
            <span className="font-medium text-hold">
              You have reached the test-mode limit, so no more credits can be bought on
              this account. Any credits you still have keep working as usual.
            </span>
          ) : (
            <>
              Each account can make up to {limits.max_purchases} test purchases, up to{" "}
              {limits.max_credits} credits in total. You have{" "}
              <span className="nums font-medium text-ink">
                {limits.purchases_left} {limits.purchases_left === 1 ? "purchase" : "purchases"}
              </span>{" "}
              and{" "}
              <span className="nums font-medium text-ink">
                {limits.credits_left} credits
              </span>{" "}
              left.
            </>
          )}
        </p>
      )}
    </div>
  );
}
