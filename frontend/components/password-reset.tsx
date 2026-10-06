"use client";

import { Loader2 } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";

function Heading({ title, lede }: { title: string; lede: string }) {
  return (
    <>
      <h1 className="text-[36px] font-semibold leading-[1.05] tracking-[-0.035em] text-ink">
        {title}
      </h1>
      <p className="mt-3 text-[16px] leading-relaxed text-ink-muted">{lede}</p>
    </>
  );
}

/** Step one: ask for the address. The answer is the same whether or not an account
 *  exists, so the page cannot be used to find out who has signed up. */
export function ForgotPasswordForm() {
  const [email, setEmail] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const send = useMutation({
    mutationFn: () => api.forgotPassword(email.trim()),
    onError: () => setError("That did not go through. Try again in a moment."),
  });

  if (send.isSuccess) {
    return (
      <div>
        <Heading
          title="Check your email"
          lede={`If an account uses ${email.trim()}, we have sent it a link to choose a new password. The link works for one hour.`}
        />
        <p className="mt-6 text-base text-muted-foreground">
          Nothing arrived? Check your spam folder, or{" "}
          <button
            type="button"
            className="text-primary"
            onClick={() => send.reset()}
          >
            try a different address
          </button>
          .
        </p>
        <p className="mt-3 text-base text-muted-foreground">
          <Link href="/login" className="text-primary">
            Back to sign in
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div>
      <Heading
        title="Reset your password"
        lede="Enter the email address you signed up with and we will send you a link to choose a new password."
      />
      <form
        className="mt-8 space-y-4 border-t border-rule pt-6"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (!email.trim()) {
            setError("Enter your email address.");
            return;
          }
          send.mutate();
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
            className="mt-1"
          />
        </div>
        {error && (
          <p role="alert" className="text-small text-sell">
            {error}
          </p>
        )}
        <Button type="submit" size="xl" className="w-full" disabled={send.isPending}>
          {send.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
          {send.isPending ? "Sending…" : "Send the reset link"}
        </Button>
      </form>
      <p className="mt-5 text-base text-muted-foreground">
        Remembered it?{" "}
        <Link href="/login" className="text-primary">
          Sign in
        </Link>
      </p>
    </div>
  );
}

/** Step two: the link from the email lands here with its token. */
export function ResetPasswordForm({ token }: { token: string }) {
  const router = useRouter();
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const reset = useMutation({
    mutationFn: () => api.resetPassword(token, password),
    onSuccess: () => {
      window.setTimeout(() => router.push("/login"), 2500);
    },
    onError: (e) => {
      const code = e instanceof ApiError ? JSON.stringify(e.payload ?? e.message) : "";
      if (code.includes("BAD_TOKEN")) {
        setError(
          "This link has expired or has already been used. Ask for a new one below.",
        );
      } else if (code.includes("INVALID_PASSWORD")) {
        setError("Choose a password of at least eight characters.");
      } else {
        setError("That did not go through. Try again in a moment.");
      }
    },
  });

  if (!token) {
    return (
      <div>
        <Heading
          title="This link is incomplete"
          lede="Open the link from your email again, or ask for a new one."
        />
        <Button asChild className="mt-6">
          <Link href="/forgot-password">Send a new link</Link>
        </Button>
      </div>
    );
  }

  if (reset.isSuccess) {
    return (
      <div>
        <Heading
          title="Password changed"
          lede="You can now sign in with your new password. Taking you there now."
        />
        <Button asChild className="mt-6">
          <Link href="/login">Sign in</Link>
        </Button>
      </div>
    );
  }

  return (
    <div>
      <Heading title="Choose a new password" lede="At least eight characters." />
      <form
        className="mt-8 space-y-4 border-t border-rule pt-6"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (password.length < 8) {
            setError("Choose a password of at least eight characters.");
            return;
          }
          if (password !== confirm) {
            setError("The two passwords do not match.");
            return;
          }
          reset.mutate();
        }}
      >
        <div>
          <Label htmlFor="password">New password</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
            className="mt-1"
          />
        </div>
        <div>
          <Label htmlFor="confirm">Type it again</Label>
          <Input
            id="confirm"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            required
            className="mt-1"
          />
        </div>
        {error && (
          <p role="alert" className="text-small text-sell">
            {error}{" "}
            {error.includes("expired") && (
              <Link href="/forgot-password" className="text-primary">
                Send a new link
              </Link>
            )}
          </p>
        )}
        <Button type="submit" size="xl" className="w-full" disabled={reset.isPending}>
          {reset.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
          {reset.isPending ? "Saving…" : "Save the new password"}
        </Button>
      </form>
    </div>
  );
}
