"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Columns3, History, LayoutDashboard, Menu, Plus, Search, Star } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { AccountMenu } from "@/components/account-menu";
import { Brand } from "@/components/brand";
import { useTickerCommand } from "@/components/ticker-command";
import { ThemeSwitch } from "@/components/theme-toggle";
import { UsageMeter } from "@/components/usage-meter";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

/** Every destination, for everyone. Nothing here is gated on an account: history, the
 *  watchlist and compare all work against the anonymous cookie. */
const NAV = [
  { href: "/analyze", label: "New analysis", Icon: Plus },
  { href: "/dashboard", label: "Dashboard", Icon: LayoutDashboard },
  { href: "/watchlist", label: "Watchlist", Icon: Star },
  { href: "/compare", label: "Compare", Icon: Columns3 },
];

function isActive(pathname: string, href: string) {
  // History is reached from the dashboard, so it lights the dashboard tab.
  if (href === "/dashboard" && pathname.startsWith("/history")) return true;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** The one header, on every page. Pill links with a mint wash for the page you are on,
 *  the search, the credit allowance, the theme and the account. */
export function SiteHeader() {
  const pathname = usePathname() ?? "/";
  const command = useTickerCommand();
  const [menuOpen, setMenuOpen] = React.useState(false);

  const { data: user, isPending: userPending } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
    staleTime: 60_000,
  });

  return (
    <header className="sticky top-0 z-40 border-b border-rule bg-paper/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[80rem] items-center gap-2 px-4 sm:px-6 lg:px-8">
        <Brand href={user ? "/dashboard" : "/"} className="mr-4 text-[18px] font-bold" markClassName="size-7" />

        <nav aria-label="Main" className="hidden items-center gap-1 lg:flex">
          {NAV.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(pathname, href) ? "page" : undefined}
              className={cn(
                "relative rounded-md px-3 py-1.5 text-[14px] transition-colors",
                isActive(pathname, href)
                  ? "font-medium text-ink"
                  : "text-ink-muted hover:bg-surface-sunk hover:text-ink",
              )}
            >
              {label}
              {/* One underline that slides between tabs as you move around the app. */}
              {isActive(pathname, href) && (
                <motion.span
                  layoutId="nav-underline"
                  aria-hidden
                  className="absolute inset-x-3 -bottom-[17px] h-[2px] rounded-full bg-ink"
                  transition={{ type: "spring", stiffness: 420, damping: 36 }}
                />
              )}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-3">
          <button
            type="button"
            onClick={command.open}
            aria-label="Search companies"
            className="flex h-9 items-center gap-2 rounded-lg border border-rule bg-surface px-2.5 text-[13px] text-ink-muted transition-colors hover:border-brand-edge hover:text-ink md:w-56 xl:w-64"
          >
            <Search className="size-4 shrink-0" />
            <span className="hidden md:inline">Search companies</span>
            <kbd className="ml-auto hidden rounded border border-rule px-1.5 font-sans text-[11px] text-ink-muted md:inline">
              ⌘K
            </kbd>
          </button>
          <UsageMeter />

          {user ? (
            <AccountMenu email={user.email} name={user.name} />
          ) : userPending ? (
            <div className="hidden w-[168px] sm:block" aria-hidden />
          ) : (
            <div className="hidden items-center gap-1 sm:flex">
              <Link
                href="/login"
                className="rounded-md px-2.5 py-1.5 text-[14px] font-medium text-ink transition-colors hover:text-ink-muted"
              >
                Sign in
              </Link>
              <Button asChild>
                <Link href="/signup">Get started</Link>
              </Button>
            </div>
          )}

          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon" className="size-9 lg:hidden" aria-label="Open menu">
                <Menu className="size-4" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-80 gap-0 bg-paper p-0">
              <SheetTitle className="border-b border-rule px-5 py-4">
                <Brand href={user ? "/dashboard" : "/"} className="text-[17px] font-bold" />
              </SheetTitle>
              <nav className="flex flex-col gap-1 p-3">
                {[...NAV, { href: "/history", label: "History", Icon: History }, { href: "/how-it-works", label: "How it works", Icon: BookOpen }].map(
                  ({ href, label, Icon }) => (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setMenuOpen(false)}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] font-medium transition-colors",
                        isActive(pathname, href)
                          ? "bg-surface-sunk text-ink"
                          : "text-ink-soft hover:bg-surface-sunk",
                      )}
                    >
                      <Icon className="size-4" />
                      {label}
                    </Link>
                  ),
                )}
              </nav>
              <div className="flex items-center justify-between border-t border-rule px-5 py-4">
                <span className="text-[14px] text-ink-muted">Theme</span>
                <ThemeSwitch />
              </div>
              {!user && !userPending && (
                <div className="mt-auto flex flex-col gap-2 border-t border-rule p-4">
                  <Button asChild size="xl">
                    <Link href="/signup" onClick={() => setMenuOpen(false)}>
                      Get started
                    </Link>
                  </Button>
                  <Button asChild variant="outline" size="xl">
                    <Link href="/login" onClick={() => setMenuOpen(false)}>
                      Sign in
                    </Link>
                  </Button>
                </div>
              )}
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
