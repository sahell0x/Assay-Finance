import { expect, test } from "@playwright/test";

test.describe("public pages", () => {
  test("landing page has one h1 and the main navigation", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1")).toHaveCount(1);
    const nav = page.locator("header nav").first();
    for (const label of ["New analysis", "Dashboard", "Watchlist", "Compare"]) {
      await expect(nav.getByRole("link", { name: label, exact: true })).toBeVisible();
    }
  });

  test("unknown analysis id renders the 404 page", async ({ page }) => {
    const res = await page.goto("/analysis/00000000-0000-0000-0000-000000000000");
    expect(res?.status()).toBe(404);
    await expect(page).toHaveTitle(/Page not found/);
    await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  });

  test("how it works shows the common questions", async ({ page }) => {
    await page.goto("/how-it-works");
    await expect(page.getByRole("heading", { name: "Common questions" })).toBeVisible();
  });
});
