"use client";

import { usePathname } from "next/navigation";
import type * as React from "react";

import { SiteFooter } from "@/components/landing/footer";
import { SiteHeader } from "@/components/site-header";

const AUTH = ["/login", "/signup", "/forgot-password", "/reset-password"];

/** Pages a visitor reads before they use anything: the front door, the method, and a
 *  memo someone shared with them. They get the full footer. */
function isMarketing(pathname: string) {
  return pathname === "/" || pathname.startsWith("/how-it-works") || pathname.startsWith("/m/");
}

/** Chooses the frame a page sits in. The sign-in pages are their own split layout with
 *  no chrome; every other page shares one header, and a full or slim footer. */
export function SiteChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";

  if (AUTH.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return (
      <main id="main" className="min-h-screen">
        {children}
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main id="main" className="flex-1">
        {children}
      </main>
      <SiteFooter slim={!isMarketing(pathname)} />
    </div>
  );
}
