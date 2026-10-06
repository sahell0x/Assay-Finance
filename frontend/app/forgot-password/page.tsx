import type { Metadata } from "next";

import { AuthLayout } from "@/components/auth-layout";
import { ForgotPasswordForm } from "@/components/password-reset";

export const metadata: Metadata = { title: "Reset your password" };

export default function ForgotPasswordPage() {
  return (
    <AuthLayout>
      <ForgotPasswordForm />
    </AuthLayout>
  );
}
