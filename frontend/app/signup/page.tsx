import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AuthLayout } from "@/components/auth-layout";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Create an account" };

export default async function SignupPage() {
  const cookieStore = await cookies();
  const sessionToken = cookieStore.get("era_session")?.value?.trim();
  if (sessionToken && sessionToken !== "deleted") {
    redirect("/dashboard");
  }

  return (
    <AuthLayout>
      <AuthForm mode="signup" />
    </AuthLayout>
  );
}
