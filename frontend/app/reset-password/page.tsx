import type { Metadata } from "next";

import { AuthLayout } from "@/components/auth-layout";
import { ResetPasswordForm } from "@/components/password-reset";

export const metadata: Metadata = { title: "Choose a new password" };

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <AuthLayout>
      <ResetPasswordForm token={token ?? ""} />
    </AuthLayout>
  );
}
