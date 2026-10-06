import { expect, test } from "@playwright/test";

/** The whole reset journey, reading the real email from Mailpit (the dev stack's local
 *  inbox). Skipped when Mailpit is not running. */
const MAILPIT = "http://localhost:8025";
const API = process.env.E2E_API_URL ?? "http://localhost:8000";

async function latestResetLink(request: import("@playwright/test").APIRequestContext, email: string) {
  for (let i = 0; i < 20; i++) {
    const res = await request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`);
    const list = (await res.json()) as { messages?: { ID: string }[] };
    const id = list.messages?.[0]?.ID;
    if (id) {
      const msg = (await (await request.get(`${MAILPIT}/api/v1/message/${id}`)).json()) as { Text: string };
      const match = msg.Text.match(/https?:\/\/\S+\/reset-password\?token=\S+/);
      if (match) return match[0];
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no reset email arrived for ${email}`);
}

test("forgot password: email link sets a new password that then signs in", async ({ page, request }) => {
  const up = await request.get(MAILPIT).catch(() => null);
  test.skip(!up || !up.ok(), "Mailpit is not running");

  const email = `reset-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  const firstPassword = "first-password-123";
  const newPassword = "second-password-456";

  // An account to reset, then signed out again.
  const reg = await request.post(`${API}/auth/register`, { data: { email, password: firstPassword } });
  expect(reg.status()).toBe(201);

  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  // Wait for the new page: the sign-in page has an Email field too.
  await expect(page.getByRole("heading", { name: "Reset your password" })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send the reset link" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  const link = await latestResetLink(request, email);
  await page.goto(link.replace(/^https?:\/\/[^/]+/, ""));
  await page.getByLabel("New password").fill(newPassword);
  await page.getByLabel("Type it again").fill(newPassword);
  await page.getByRole("button", { name: "Save the new password" }).click();
  await expect(page.getByRole("heading", { name: "Password changed" })).toBeVisible();

  // The old password no longer works; the new one does.
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(firstPassword);
  await page.locator("form button[type=submit]").click();
  await expect(page.locator("p[role=alert]")).toContainText("do not match");
  await page.getByLabel("Password", { exact: true }).fill(newPassword);
  await page.locator("form button[type=submit]").click();
  await expect(page).toHaveURL(/\/dashboard/);

  // A used link cannot be used again.
  await page.goto(link.replace(/^https?:\/\/[^/]+/, ""));
  await page.getByLabel("New password").fill("third-password-789");
  await page.getByLabel("Type it again").fill("third-password-789");
  await page.getByRole("button", { name: "Save the new password" }).click();
  await expect(page.locator("p[role=alert]")).toContainText("expired or has already been used");
});
