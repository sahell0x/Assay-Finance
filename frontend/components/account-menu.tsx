"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { History, LayoutDashboard, LogOut, Moon, Sun, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useDarkMode } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";

/** The signed-in person's menu. Shared by the landing nav and the app top bar. */
export function AccountMenu({ email, name }: { email: string; name?: string | null }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const initial = (name || email).trim().charAt(0).toUpperCase();
  const { dark, setDark } = useDarkMode();

  const signOut = useMutation({
    mutationFn: () => api.logout(),
    onSettled: () => {
      queryClient.clear();
      router.push("/");
      router.refresh();
    },
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="group size-9 rounded-full" aria-label="Account">
          <span className="grid size-8 place-items-center rounded-full bg-ink text-[13px] font-semibold text-paper ring-2 ring-transparent ring-offset-2 ring-offset-paper transition-[box-shadow] duration-200 group-hover:ring-brand-edge">
            {initial}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={10}
        className="min-w-60 origin-(--radix-dropdown-menu-content-transform-origin) rounded-xl p-1.5 shadow-lift duration-200 data-[state=open]:slide-in-from-top-2"
      >
        <DropdownMenuLabel className="font-normal">
          <p className="text-base font-medium text-ink">{name || "Signed in"}</p>
          <p className="truncate text-small text-muted-foreground">{email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/dashboard">
            <LayoutDashboard className="size-4" />
            Dashboard
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/history">
            <History className="size-4" />
            History
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/credits">
            <Zap className="size-4" />
            Credits &amp; billing
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setDark(!dark)}>
          {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          {dark ? "Light mode" : "Dark mode"}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => signOut.mutate()}>
          <LogOut className="size-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
