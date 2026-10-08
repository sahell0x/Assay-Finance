"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { EASE } from "@/components/landing/motion";
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

/** Forgot password flow with 6-digit email OTP verification. */
export function ForgotPasswordForm() {
  const router = useRouter();
  const queryClient = useQueryClient();

  // If user is already authenticated with email, pre-fill email
  const { data: currentUser } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    staleTime: 60_000,
  });

  const [typedEmail, setTypedEmail] = React.useState<string | null>(null);
  const email = typedEmail !== null ? typedEmail : (currentUser?.email ?? "");
  const setEmail = (val: string) => setTypedEmail(val);

  const [step, setStep] = React.useState<"email" | "otp">("email");
  const [otpDigits, setOtpDigits] = React.useState<string[]>(["", "", "", "", "", ""]);
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [showNewPassword, setShowNewPassword] = React.useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [info, setInfo] = React.useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = React.useState<number>(0);
  const [resetSuccess, setResetSuccess] = React.useState(false);

  const otpInputRefs = React.useRef<(HTMLInputElement | null)[]>([]);

  // Resend cooldown timer countdown
  React.useEffect(() => {
    if (resendCooldown <= 0) return;
    const interval = setInterval(() => {
      setResendCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [resendCooldown]);

  // Step 1: Send Password Reset OTP mutation
  const sendOtpMutation = useMutation({
    mutationFn: async () => {
      return await api.sendPasswordResetOtp(email.trim());
    },
    onSuccess: () => {
      setStep("otp");
      setResendCooldown(60);
      setError(null);
      setInfo(`We sent a 6-digit verification code to ${email.trim()}.`);
      setOtpDigits(["", "", "", "", "", ""]);
      setTimeout(() => {
        otpInputRefs.current[0]?.focus();
      }, 50);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 404) {
        setError("No account found with that email address. Check your spelling or sign up.");
        return;
      }
      if (e instanceof ApiError && e.status === 429) {
        const detail = e.payload as { message?: string } | undefined;
        setError(detail?.message ?? "Please wait before requesting another code.");
        return;
      }
      setError(
        e instanceof ApiError ? e.message : "Could not send verification code. Try again in a moment.",
      );
    },
  });

  // Step 2: Verify Password Reset OTP and set new password
  const verifyOtpMutation = useMutation({
    mutationFn: async (otpCode: string) => {
      return await api.verifyPasswordResetOtp({
        email: email.trim(),
        otp: otpCode,
        password: newPassword,
      });
    },
    onSuccess: () => {
      queryClient.clear();
      setResetSuccess(true);
      window.setTimeout(() => {
        router.push("/dashboard");
        router.refresh();
      }, 2000);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        const detail = e.payload as { code?: string; message?: string; reason?: string } | undefined;
        if (detail?.code === "RESET_PASSWORD_INVALID_PASSWORD") {
          setError(detail.reason ?? detail.message ?? "Use a password of at least eight characters.");
          return;
        }
        if (detail?.code === "OTP_EXPIRED") {
          setError("Verification code has expired. Please request a new one.");
          return;
        }
        if (detail?.message) {
          setError(detail.message);
          return;
        }
      }
      setError(
        e instanceof ApiError ? e.message : "Invalid verification code. Please check and try again.",
      );
    },
  });

  const fullOtp = otpDigits.join("");

  const handleOtpChange = (index: number, value: string) => {
    setError(null);
    setInfo(null);
    const digitsOnly = value.replace(/\D/g, "");
    if (!digitsOnly) {
      const next = [...otpDigits];
      next[index] = "";
      setOtpDigits(next);
      return;
    }

    const next = [...otpDigits];
    next[index] = digitsOnly.slice(-1);
    setOtpDigits(next);

    if (index < 5) {
      otpInputRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !otpDigits[index] && index > 0) {
      otpInputRefs.current[index - 1]?.focus();
    } else if (e.key === "ArrowLeft" && index > 0) {
      otpInputRefs.current[index - 1]?.focus();
    } else if (e.key === "ArrowRight" && index < 5) {
      otpInputRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpPaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasted) return;

    const next = [...otpDigits];
    for (let i = 0; i < 6; i++) {
      next[i] = pasted[i] || "";
    }
    setOtpDigits(next);

    const targetFocus = Math.min(pasted.length, 5);
    otpInputRefs.current[targetFocus]?.focus();
  };

  const handleResend = () => {
    if (resendCooldown > 0 || sendOtpMutation.isPending) return;
    setError(null);
    sendOtpMutation.mutate();
  };

  const reduced = useReducedMotion();
  const rise = (delay: number) => ({
    initial: reduced ? false : { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.55, ease: EASE, delay },
  });

  if (resetSuccess) {
    return (
      <motion.div {...rise(0)}>
        <div className="flex size-12 items-center justify-center rounded-2xl bg-buy-fill/15 text-primary mb-4">
          <CheckCircle2 className="size-6 text-primary" />
        </div>
        <Heading
          title="Password changed"
          lede="Your new password has been saved and your account is signed in. Taking you to your dashboard…"
        />
        <div className="mt-6 flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/dashboard">Go to dashboard</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/login">Sign in</Link>
          </Button>
        </div>
      </motion.div>
    );
  }

  if (step === "otp") {
    return (
      <motion.div {...rise(0)}>
        <button
          type="button"
          onClick={() => {
            setStep("email");
            setError(null);
            setInfo(null);
          }}
          className="mb-5 inline-flex items-center gap-1.5 text-small text-ink-muted hover:text-ink transition-colors"
        >
          <ArrowLeft className="size-4" />
          Change email address
        </button>

        <div className="flex items-center gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface-sunk text-primary">
            <KeyRound className="size-5" />
          </div>
          <div>
            <h1 className="text-[28px] font-semibold leading-[1.1] tracking-[-0.035em] text-ink">
              Enter verification code
            </h1>
            <p className="mt-1 text-small text-ink-muted">
              We sent a 6-digit code to <strong className="text-ink font-medium">{email.trim()}</strong>
            </p>
          </div>
        </div>

        <form
          className="mt-8 space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (fullOtp.length !== 6) {
              setError("Please enter the complete 6-digit verification code.");
              return;
            }
            if (newPassword.length < 8) {
              setError("Choose a password of at least eight characters.");
              return;
            }
            if (newPassword.toLowerCase() === email.trim().toLowerCase()) {
              setError("Do not use your email address as your password.");
              return;
            }
            if (newPassword !== confirmPassword) {
              setError("The two passwords do not match.");
              return;
            }
            verifyOtpMutation.mutate(fullOtp);
          }}
        >
          <div>
            <Label className="block text-center text-micro text-ink-muted uppercase tracking-wider mb-3">
              Security Verification Code
            </Label>
            <div
              className="flex items-center justify-between gap-2 sm:gap-2.5"
              onPaste={handleOtpPaste}
            >
              {otpDigits.map((digit, idx) => (
                <input
                  key={idx}
                  ref={(el) => {
                    otpInputRefs.current[idx] = el;
                  }}
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={1}
                  autoComplete="one-time-code"
                  value={digit}
                  aria-label={`Digit ${idx + 1}`}
                  onChange={(e) => handleOtpChange(idx, e.target.value)}
                  onKeyDown={(e) => handleOtpKeyDown(idx, e)}
                  className="size-11 sm:size-12 rounded-lg border border-rule bg-surface text-center font-mono text-2xl font-bold text-ink transition-all focus:border-primary focus:bg-background focus:ring-2 focus:ring-primary/20 focus:outline-none"
                />
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between text-small">
            <span className="text-ink-muted">Didn&apos;t receive the code?</span>
            {resendCooldown > 0 ? (
              <span className="text-muted-foreground font-mono text-xs">
                Resend in {resendCooldown}s
              </span>
            ) : (
              <button
                type="button"
                onClick={handleResend}
                disabled={sendOtpMutation.isPending}
                className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline disabled:opacity-50"
              >
                {sendOtpMutation.isPending ? (
                  <RefreshCw className="size-3.5 animate-spin" />
                ) : null}
                Resend code
              </button>
            )}
          </div>

          <div>
            <Label htmlFor="new-password">New password</Label>
            <div className="relative mt-1.5">
              <Input
                id="new-password"
                type={showNewPassword ? "text" : "password"}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                required
                className="h-11 pr-10 transition-shadow focus-visible:shadow-float"
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShowNewPassword((prev) => !prev)}
                aria-label={showNewPassword ? "Hide password" : "Show password"}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-ink transition-colors focus:outline-none"
              >
                {showNewPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span className="h-1 flex-1 overflow-hidden rounded-full bg-surface-sunk">
                <motion.span
                  className={newPassword.length >= 8 ? "block h-full rounded-full bg-buy-fill" : "block h-full rounded-full bg-ink/40"}
                  initial={false}
                  animate={{ width: `${Math.min(100, (newPassword.length / 8) * 100)}%` }}
                  transition={{ duration: 0.25 }}
                />
              </span>
              <span className="text-micro text-muted-foreground">
                {newPassword.length >= 8 ? "Long enough" : "At least eight characters"}
              </span>
            </div>
          </div>

          <div>
            <Label htmlFor="confirm-password">Confirm new password</Label>
            <div className="relative mt-1.5">
              <Input
                id="confirm-password"
                type={showConfirmPassword ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
                className="h-11 pr-10 transition-shadow focus-visible:shadow-float"
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShowConfirmPassword((prev) => !prev)}
                aria-label={showConfirmPassword ? "Hide password" : "Show password"}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-ink transition-colors focus:outline-none"
              >
                {showConfirmPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>

          <AnimatePresence initial={false}>
            {info && !error && (
              <motion.p
                key="info"
                initial={{ opacity: 0, y: -4, height: 0 }}
                animate={{ opacity: 1, y: 0, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="rounded-lg bg-surface-sunk px-3 py-2 text-small text-ink-muted text-center"
              >
                {info}
              </motion.p>
            )}
            {error && (
              <motion.p
                key={error}
                role="alert"
                initial={{ opacity: 0, y: -4, height: 0 }}
                animate={{ opacity: 1, y: 0, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden text-small text-sell text-center"
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>

          <Button
            type="submit"
            size="xl"
            className="w-full"
            disabled={verifyOtpMutation.isPending || fullOtp.length !== 6 || !newPassword}
          >
            {verifyOtpMutation.isPending && (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            )}
            {verifyOtpMutation.isPending ? "Resetting password…" : "Reset password"}
          </Button>
        </form>
      </motion.div>
    );
  }

  return (
    <motion.div {...rise(0)}>
      <Heading
        title="Reset your password"
        lede="Enter the email address you signed up with and we will send you a 6-digit verification code to set a new password."
      />

      <form
        className="mt-8 space-y-4 border-t border-rule pt-6"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          setInfo(null);
          if (!email.trim()) {
            setError("Enter your email address.");
            return;
          }
          sendOtpMutation.mutate();
        }}
      >
        <div>
          <Label htmlFor="email">Email</Label>
          <div className="relative mt-1.5">
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              className="h-11 transition-shadow focus-visible:shadow-float"
            />
          </div>
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

        <Button
          type="submit"
          size="xl"
          className="w-full"
          disabled={sendOtpMutation.isPending || !email.trim()}
        >
          {sendOtpMutation.isPending && (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          )}
          {sendOtpMutation.isPending ? "Sending code…" : "Send verification code"}
        </Button>
      </form>

      <p className="mt-5 text-base text-muted-foreground">
        Remembered your password?{" "}
        <Link href="/login" className="text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </motion.div>
  );
}

/** Step two for magic link flow (backwards compatibility for ?token=... links). */
export function ResetPasswordForm({ token }: { token: string }) {
  const router = useRouter();
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [showConfirm, setShowConfirm] = React.useState(false);
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
          "This link has expired or has already been used. Ask for a new code below.",
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
          title="Reset link missing"
          lede="Please request a verification code to choose a new password."
        />
        <Button asChild className="mt-6">
          <Link href="/forgot-password">Reset password with code</Link>
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
          <div className="relative mt-1">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
              className="h-11 pr-10"
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShowPassword((prev) => !prev)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-ink transition-colors focus:outline-none"
            >
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
        <div>
          <Label htmlFor="confirm">Type it again</Label>
          <div className="relative mt-1">
            <Input
              id="confirm"
              type={showConfirm ? "text" : "password"}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              required
              className="h-11 pr-10"
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShowConfirm((prev) => !prev)}
              aria-label={showConfirm ? "Hide password" : "Show password"}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-ink transition-colors focus:outline-none"
            >
              {showConfirm ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
        {error && (
          <p role="alert" className="text-small text-sell">
            {error}{" "}
            {error.includes("expired") && (
              <Link href="/forgot-password" className="text-primary hover:underline">
                Send a new code
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
