"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2 } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { EASE } from "@/components/landing/motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";

/** What an account actually adds. Everything not on this list already works without one,
 *  which is the reason the list is short and specific rather than a sales pitch. */
const BENEFITS = [
  "Ten more free analyses, on top of your first three",
  "History and watchlists that follow you between devices",
  "Score tracking for a company across every run",
];

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const submit = useMutation({
    mutationFn: async () => {
      if (mode === "signup") {
        await api.register(email, password);
      }
      await api.login(email, password);
    },
    onSuccess: () => {
      // Everything cached so far belongs to the signed-out visitor: the header's
      // "Sign in" state, 3 free credits, the anonymous history. Drop it so the
      // dashboard loads as the account rather than showing the old view until a reload.
      queryClient.clear();
      router.push("/dashboard");
      router.refresh();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400 && mode === "signup") {
        const detail = e.payload as { code?: string; reason?: string } | undefined;
        if (detail?.code === "REGISTER_INVALID_PASSWORD") {
          setError(detail.reason ?? "Use a password of at least eight characters.");
        } else {
          setError("An account already exists for that address. Sign in instead.");
        }
        return;
      }
      setError(
        e instanceof ApiError ? e.message : "That did not work. Try again in a moment.",
      );
    },
  });

  const reduced = useReducedMotion();
  const rise = (delay: number) => ({
    initial: reduced ? false : { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.55, ease: EASE, delay },
  });

  return (
    <motion.div {...rise(0)}>
      <h1 className="text-[36px] font-semibold leading-[1.05] tracking-[-0.035em] text-ink">
        {mode === "signup" ? "Create an account" : "Sign in"}
      </h1>
      <p className="mt-3 text-[16px] leading-relaxed text-ink-muted">
        {mode === "signup"
          ? "Everything you have already run moves across with you. Nothing you have done so far is lost."
          : "Your history, watchlists and score tracking are waiting."}
      </p>

      {mode === "signup" && (
        <ul className="mt-5 space-y-1.5">
          {BENEFITS.map((b) => (
            <li
              key={b}
              className="flex gap-2.5 text-base leading-relaxed text-ink-soft"
            >
              <Check className="mt-1 size-3.5 shrink-0 text-primary" strokeWidth={2.5} />
              {b}
            </li>
          ))}
        </ul>
      )}

      <motion.div {...rise(0.12)} className="mt-8">
        <div>
      <Button asChild size="xl" variant="outline" className="w-full">
        <a href={api.googleAuthorizeUrl()}>Continue with Google</a>
      </Button>

      <div className="my-5 flex items-center gap-3">
        <span className="h-px flex-1 bg-rule" />
        <span className="text-micro text-muted-foreground">or use an email address</span>
        <span className="h-px flex-1 bg-rule" />
      </div>

      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (!email.trim() || !password) {
            setError("Enter an email address and a password.");
            return;
          }
          if (mode === "signup" && password.length < 8) {
            setError("Use a password of at least eight characters.");
            return;
          }
          submit.mutate();
        }}
      >
        <div>
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            className="mt-1.5 h-11 transition-shadow focus-visible:shadow-float"
          />
        </div>

        <div>
          <div className="flex items-baseline justify-between gap-3">
            <Label htmlFor="password">Password</Label>
            {mode === "login" && (
              <Link href="/forgot-password" className="text-small text-primary">
                Forgot password?
              </Link>
            )}
          </div>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            required
            className="mt-1.5 h-11 transition-shadow focus-visible:shadow-float"
          />
          {mode === "signup" && (
            <div className="mt-2 flex items-center gap-2">
              <span className="h-1 flex-1 overflow-hidden rounded-full bg-surface-sunk">
                <motion.span
                  className={password.length >= 8 ? "block h-full rounded-full bg-buy-fill" : "block h-full rounded-full bg-ink/40"}
                  initial={false}
                  animate={{ width: `${Math.min(100, (password.length / 8) * 100)}%` }}
                  transition={{ duration: 0.25 }}
                />
              </span>
              <span className="text-micro text-muted-foreground">
                {password.length >= 8 ? "Long enough" : "At least eight characters"}
              </span>
            </div>
          )}
        </div>

        <AnimatePresence initial={false}>
          {error && (
            <motion.p
              key={error}
              role="alert"
              initial={{ opacity: 0, y: -4, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden text-small text-sell"
            >
              {error}
            </motion.p>
          )}
        </AnimatePresence>

        <Button type="submit" size="xl" className="w-full" disabled={submit.isPending}>
          {submit.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
          {submit.isPending
            ? mode === "signup"
              ? "Creating your account…"
              : "Signing in…"
            : mode === "signup"
              ? "Create the account"
              : "Sign in"}
        </Button>
      </form>
        </div>
      </motion.div>

      <p className="mt-5 text-base text-muted-foreground">
        {mode === "signup" ? (
          <>
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </>
        ) : (
          <>
            No account yet?{" "}
            <Link href="/signup" className="text-primary hover:underline">
              Create one
            </Link>
          </>
        )}
      </p>
    </motion.div>
  );
}
