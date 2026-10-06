import { expect, test } from "@playwright/test";

/* Only free flows here. POST /analyses with "APPLE" is refused by the API before
 * anything is charged (unknown_ticker); nothing in this file submits a real ticker. */

test("a company name typed as a ticker is refused with suggestions", async ({ page }) => {
  await page.goto("/analyze");
  const field = page.getByLabel("Company", { exact: true });
  await field.fill("APPLE");
  await expect(field).toHaveValue("APPLE");

  const refused = page.waitForResponse(
    (r) => r.url().includes("/analyses") && r.request().method() === "POST",
  );
  await field.press("Enter");
  const res = await refused;
  expect(res.status()).toBe(422);

  await expect(page.getByText("APPLE is not a stock ticker we recognize")).toBeVisible();
  const didYouMean = page.getByRole("list", { name: "Did you mean" });
  await expect(didYouMean).toBeVisible();
  await expect(didYouMean.getByRole("button", { name: /AAPL/ })).toBeVisible();
});

test.describe("watchlist add", () => {
  test("a name with no match is rejected", async ({ page }) => {
    await page.goto("/watchlist");
    const field = page.getByLabel("Ticker to add");
    await field.fill("GOOGLE");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    // The ticker search now knows GOOGLE as a name for Alphabet, so the refusal points at
    // the suggestions instead of saying nothing was found. Either way it is not added.
    await expect(
      page
        .getByRole("alert")
        .filter({ hasText: /No company found for GOOGLE|GOOGLE is not a ticker/ }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "GOOGLE", exact: true })).toHaveCount(0);
  });

  test("typing shows suggestion chips", async ({ page }) => {
    await page.goto("/watchlist");
    await page.getByLabel("Ticker to add").fill("MS");
    await expect(page.getByRole("button", { name: /^MS\s*Morgan Stanley$/i })).toBeVisible();
  });
});
