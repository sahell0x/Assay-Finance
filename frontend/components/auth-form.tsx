"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Eye, EyeOff, Loader2, Mail, RefreshCw } from "lucide-react";
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
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [info, setInfo] = React.useState<string | null>(null);

  // Signup OTP step state: "details" -> "otp"
  const [step, setStep] = React.useState<"details" | "otp">("details");
  const [otpDigits, setOtpDigits] = React.useState<string[]>(["", "", "", "", "", ""]);
  const [resendCooldown, setResendCooldown] = React.useState<number>(0);
  const otpInputRefs = React.useRef<(HTMLInputElement | null)[]>([]);

  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    staleTime: 60_000,
  });

  React.useEffect(() => {
    if (user) {
      router.replace("/dashboard");
    }
  }, [user, router]);

  // Resend cooldown timer countdown
  React.useEffect(() => {
    if (resendCooldown <= 0) return;
    const interval = setInterval(() => {
      setResendCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [resendCooldown]);

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: async () => {
      await api.login(email, password);
    },
    onSuccess: () => {
      queryClient.clear();
      router.push("/dashboard");
      router.refresh();
    },
    onError: (e) => {
      setError(
        e instanceof ApiError ? e.message : "That did not work. Try again in a moment.",
      );
    },
  });

  // Step 1: Send OTP mutation
  const sendOtpMutation = useMutation({
    mutationFn: async () => {
      return await api.sendSignupOtp(email);
    },
    onSuccess: () => {
      setStep("otp");
      setResendCooldown(60);
      setError(null);
      setInfo(`We sent a 6-digit verification code to ${email}.`);
      setOtpDigits(["", "", "", "", "", ""]);
      setTimeout(() => {
        otpInputRefs.current[0]?.focus();
      }, 50);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        const detail = e.payload as { code?: string; message?: string } | undefined;
        if (detail?.code === "EMAIL_ALREADY_EXISTS") {
          setError("An account already exists for that address. Sign in instead.");
          return;
        }
      }
      setError(
        e instanceof ApiError ? e.message : "Could not send verification code. Try again in a moment.",
      );
    },
  });

  // Step 2: Verify OTP and Register mutation
  const verifyOtpMutation = useMutation({
    mutationFn: async (code: string) => {
      return await api.verifySignupOtp({
        email,
        password,
        otp: code,
      });
    },
    onSuccess: () => {
      queryClient.clear();
      router.push("/dashboard");
      router.refresh();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        const detail = e.payload as { code?: string; message?: string; reason?: string } | undefined;
        if (detail?.code === "REGISTER_INVALID_PASSWORD") {
          setError(detail.reason ?? detail.message ?? "Use a password of at least eight characters.");
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
    // Allow only numeric characters
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

    // Auto focus next box if not on the last box
    if (index < 5) {
      otpInputRefs.current[index + 1]?.focus();
    } else {
      // If filling the last box and all 6 are complete, trigger auto-submit
      const completeCode = next.join("");
      if (completeCode.length === 6) {
        verifyOtpMutation.mutate(completeCode);
      }
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

    if (pasted.length === 6) {
      verifyOtpMutation.mutate(pasted);
    }
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

  return (
    <motion.div {...rise(0)}>
      {mode === "signup" && step === "otp" ? (
        <div>
          <button
            type="button"
            onClick={() => {
              setStep("details");
              setError(null);
              setInfo(null);
            }}
            className="mb-5 inline-flex items-center gap-1.5 text-small text-ink-muted hover:text-ink transition-colors"
          >
            <ArrowLeft className="size-4" />
            Back to account details
          </button>

          <div className="flex items-center gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface-sunk text-primary">
              <Mail className="size-5" />
            </div>
            <div>
              <h1 className="text-[28px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink">
                Verify your email
              </h1>
              <p className="mt-1 text-small text-ink-muted">
                Enter the 6-digit code sent to <strong className="text-ink font-medium">{email}</strong>
              </p>
            </div>
          </div>

          <form
            className="mt-8 space-y-6"
            onSubmit={(e) => {
              e.preventDefault();
              if (fullOtp.length !== 6) {
                setError("Please enter the complete 6-digit verification code.");
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
              <span className="text-ink-muted">Didn&apos;t get the code?</span>
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
              disabled={verifyOtpMutation.isPending || fullOtp.length !== 6}
            >
              {verifyOtpMutation.isPending && (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              )}
              {verifyOtpMutation.isPending ? "Verifying & creating account…" : "Verify and create account"}
            </Button>
          </form>
        </div>
      ) : (
        <div>
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
                  setInfo(null);
                  if (!email.trim() || !password) {
                    setError("Enter an email address and a password.");
                    return;
                  }
                  if (mode === "signup") {
                    if (password.length < 8) {
                      setError("Use a password of at least eight characters.");
                      return;
                    }
                    if (password.toLowerCase() === email.toLowerCase()) {
                      setError("Do not use your email address as your password.");
                      return;
                    }
                    if (!confirmPassword) {
                      setError("Please confirm your password.");
                      return;
                    }
                    if (password !== confirmPassword) {
                      setError("Passwords do not match.");
                      return;
                    }
                    sendOtpMutation.mutate();
                  } else {
                    loginMutation.mutate();
                  }
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
                      <Link href="/forgot-password" className="text-small text-primary hover:underline">
                        Forgot password?
                      </Link>
                    )}
                  </div>
                  <div className="relative mt-1.5">
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete={mode === "signup" ? "new-password" : "current-password"}
                      required
                      className="h-11 pr-10 transition-shadow focus-visible:shadow-float"
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

                {mode === "signup" && (
                  <div>
                    <Label htmlFor="confirm-password">Confirm password</Label>
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
                )}

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
                  disabled={sendOtpMutation.isPending || loginMutation.isPending}
                >
                  {(sendOtpMutation.isPending || loginMutation.isPending) && (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  )}
                  {mode === "signup"
                    ? sendOtpMutation.isPending
                      ? "Sending verification code…"
                      : "Continue"
                    : loginMutation.isPending
                      ? "Signing in…"
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
        </div>
      )}
    </motion.div>
  );
}
