import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_URL ?? "http://localhost:8000";

test("security headers are set on the landing page", async ({ request }) => {
  const res = await request.get("/");
  expect(res.ok()).toBeTruthy();
  const h = res.headers();
  expect(h["x-frame-options"]).toBe("DENY");
  expect(h["x-content-type-options"]).toBe("nosniff");
});

test("session endpoint without cookies returns null", async ({ playwright }) => {
  const ctx = await playwright.request.newContext();
  const res = await ctx.get(`${API}/auth/session`);
  expect(res.status()).toBe(200);
  expect(await res.json()).toBeNull();
  await ctx.dispose();
});

test("public analysis payload hides cost and trace data", async ({ request }) => {
  const showcase = await request.get(`${API}/public/showcase?limit=1`);
  expect(showcase.ok()).toBeTruthy();
  const cards = (await showcase.json()) as { id: string }[];
  test.skip(!Array.isArray(cards) || cards.length === 0, "showcase is empty");

  const res = await request.get(`${API}/analyses/${cards[0].id}`);
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).not.toHaveProperty("cost_usd");
  expect(body).not.toHaveProperty("trace");
  if (body.blocks) expect(body.blocks).not.toHaveProperty("cost");
});
