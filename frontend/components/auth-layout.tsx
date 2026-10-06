import type * as React from "react";

import { AuthAside } from "@/components/app/auth-aside";
import { Brand } from "@/components/brand";
import { fetchShowcase } from "@/lib/api";

/** The sign-in frame: the form on the left, and on the right the thing an account is
 *  for, a real report being worked out, so the page argues for itself. If nothing has
 *  been analyzed yet the panel simply lists what an account adds. */
export async function AuthLayout({ children }: { children: React.ReactNode }) {
  const cards = await fetchShowcase(6);

  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div className="flex flex-col px-5 py-6 sm:px-10">
        <Brand className="text-[20px] font-semibold" markClassName="size-7" />
        <div className="flex flex-1 items-center py-12">
          <div className="mx-auto w-full max-w-[26rem]">{children}</div>
        </div>
        <p className="text-[12px] leading-relaxed text-faint">
          For information only. This is not investment advice.
        </p>
      </div>

      <aside
        aria-label="What you get"
        className="relative hidden overflow-hidden border-l border-rule bg-surface lg:flex lg:flex-col lg:justify-center lg:px-14 xl:px-20"
      >
        <AuthAside cards={cards} />
      </aside>
    </div>
  );
}
