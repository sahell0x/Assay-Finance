"use client";

import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { api } from "@/lib/api";

/** If a signed-in user opens the landing page in the browser, redirect them directly
 *  to the dashboard.
 */
export function LandingAuthRedirect() {
  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    staleTime: 60_000,
  });

  React.useEffect(() => {
    if (user) {
      window.location.replace("/dashboard");
    }
  }, [user]);

  return null;
}
