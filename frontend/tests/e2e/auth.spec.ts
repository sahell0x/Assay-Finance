import { expect, test } from "@playwright/test";

test("sign up lands on the dashboard signed in, then sign out", async ({ page }) => {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;

  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create the account" }).click();

  await expect(page).toHaveURL(/\/dashboard/);
  const header = page.locator("header").first();
  // No reload: the header must switch to the account without one.
  const meter = header.getByRole("link", { name: /credits left/ });
  await expect(meter).toBeVisible();
  // A new account starts with free_account_credits (10, backend/src/config.py).
  await expect(meter).toContainText("10");
  await expect(header.getByRole("link", { name: "Sign in" })).toHaveCount(0);

  await header.getByRole("button", { name: "Account" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(header.getByRole("link", { name: "Sign in" })).toBeVisible();
});

test("signed-in user opening landing page or auth pages redirects to dashboard", async ({ page }) => {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;

  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create the account" }).click();

  await expect(page).toHaveURL(/\/dashboard/);

  // Opening the website / landing page again should go directly to the dashboard
  await page.goto("/");
  await expect(page).toHaveURL(/\/dashboard/);

  // Visiting login or signup should also redirect to dashboard
  await page.goto("/login");
  await expect(page).toHaveURL(/\/dashboard/);

  await page.goto("/signup");
  await expect(page).toHaveURL(/\/dashboard/);
});

