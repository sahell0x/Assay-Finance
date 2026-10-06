"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import * as React from "react";

import { cn } from "@/lib/cn";

const subscribeToNothing = () => () => {};

/** "Am I on the client yet" without a setState in an effect: the server snapshot is
 *  false during hydration, the client one true afterwards. Until then the resolved theme
 *  is unknown, and rendering a guess would flip after hydration. */
function useMounted() {
  return React.useSyncExternalStore(
    subscribeToNothing,
    () => true,
    () => false,
  );
}

export function useDarkMode() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();
  const dark = mounted && resolvedTheme === "dark";
  return { mounted, dark, setDark: (on: boolean) => setTheme(on ? "dark" : "light") };
}

/** A two-option segmented switch, "Light | Dark". It lives in the footer and the
 *  account menu rather than the header, so the header stays about the product. */
export function ThemeSwitch({ className }: { className?: string }) {
  const { mounted, dark, setDark } = useDarkMode();

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className={cn("inline-flex rounded-lg border border-rule bg-paper p-0.5", className)}
    >
      {[
        { on: false, label: "Light", Icon: Sun },
        { on: true, label: "Dark", Icon: Moon },
      ].map(({ on, label, Icon }) => {
        const active = mounted && dark === on;
        return (
          <button
            key={label}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setDark(on)}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[12px] font-medium transition-colors",
              active ? "bg-surface-sunk text-ink" : "text-ink-muted hover:text-ink",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
            {label}
          </button>
        );
      })}
    </div>
  );
}
