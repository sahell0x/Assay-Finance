/** HTTP client.
 *
 *  Every request sends credentials: the session and the anonymous-visitor id both
 *  live in httpOnly cookies, so a request without them is a request from nobody.
 */

import type {
  ActivityFilter,
  AnalysisAccepted,
  AnalysisDetail,
  AnalysisSummary,
  BillingSummary,
  CompareColumn,
  CreditActivity,
  CreditOrder,
  CreditPacks,
  CurrentUser,
  HistoryPoint,
  PaymentConfirmation,
  PaymentRecord,
  ScenarioResult,
  ScenarioSetup,
  ShowcaseCard,
  TickerResolution,
  TickerSuggestion,
  UsageState,
  WatchlistEntry,
} from "./types";

/** The public API base the browser uses. */
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/** The API base the Next server uses for server-rendered fetches. */
export const SERVER_API_URL =
  process.env.BACKEND_URL?.replace(/\/$/, "") ||
  API_URL;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
    public payload?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Turn any failure into something the interface can say out loud. */
async function toError(res: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = (await res.json())?.detail;
  } catch {
    detail = undefined;
  }

  if (detail && typeof detail === "object") {
    const d = detail as { code?: string; message?: string };
    return new ApiError(res.status, d.message ?? res.statusText, d.code, detail);
  }
  if (typeof detail === "string") {
    return new ApiError(res.status, detail);
  }

  const fallback: Record<number, string> = {
    401: "Sign in to do that.",
    403: "That belongs to someone else.",
    404: "That does not exist.",
    409: "That is not ready yet.",
    422: "Check the values you entered.",
    429: "You have used your allowance for now.",
    503: "The service is briefly unavailable. Try again in a moment.",
  };
  return new ApiError(res.status, fallback[res.status] ?? "Something went wrong.");
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/* ------------------------------------------------------------------ analyses */

export interface RunRequest {
  ticker: string;
  peer_tickers?: string[];
  weights?: Record<string, number>;
  force_refresh?: boolean;
}

export const api = {
  runAnalysis: (body: RunRequest) =>
    request<AnalysisAccepted>("/analyses", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getAnalysis: (id: string) => request<AnalysisDetail>(`/analyses/${id}`),

  listAnalyses: (params: { ticker?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.ticker) q.set("ticker", params.ticker);
    if (params.limit) q.set("limit", String(params.limit));
    const qs = q.toString();
    return request<AnalysisSummary[]>(`/analyses${qs ? `?${qs}` : ""}`);
  },

  deleteAnalysis: (id: string) =>
    request<void>(`/analyses/${id}`, { method: "DELETE" }),

  /* ------------------------------------------------------------- scenarios */

  /** What can be varied, and what would change the rating. */
  scenarioSetup: (id: string, target?: string) =>
    request<ScenarioSetup>(
      `/analyses/${id}/scenario${target ? `?target=${encodeURIComponent(target)}` : ""}`,
    ),

  /** Re-run the rubric with some inputs moved. Costs nothing: no queue, no model. */
  runScenario: (
    id: string,
    body: { overrides?: Record<string, number>; weights?: Record<string, number> },
  ) =>
    request<ScenarioResult>(`/analyses/${id}/scenario`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  shareAnalysis: (id: string) =>
    request<{ slug: string; url: string }>(`/analyses/${id}/share`, { method: "POST" }),

  publicMemo: (slug: string) => request<AnalysisDetail>(`/public/${slug}`),

  sample: () => request<AnalysisDetail>("/public/sample/memo"),

  showcase: (limit = 6) => request<ShowcaseCard[]>(`/public/showcase?limit=${limit}`),

  pdfUrl: (id: string) => `${API_URL}/analyses/${id}/pdf`,

  /* -------------------------------------------------------------- tickers */

  searchTickers: (q: string) =>
    request<TickerSuggestion[]>(`/tickers/search?q=${encodeURIComponent(q)}`),

  resolveTickers: (q: string) =>
    request<TickerResolution>(`/tickers/resolve?q=${encodeURIComponent(q)}`),

  tickerHistory: (ticker: string) =>
    request<HistoryPoint[]>(`/tickers/${encodeURIComponent(ticker)}/history`),

  /* ------------------------------------------------------------ watchlist */

  watchlist: () => request<WatchlistEntry[]>("/watchlist"),

  addWatch: (ticker: string) =>
    request<{ ticker: string }>(`/watchlist/${encodeURIComponent(ticker)}`, {
      method: "POST",
    }),

  removeWatch: (ticker: string) =>
    request<void>(`/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }),

  compare: (tickers: string[]) =>
    request<{ columns: CompareColumn[]; missing: string[]; dimensions: string[] }>(
      `/compare?tickers=${encodeURIComponent(tickers.join(","))}`,
    ),

  /* ---------------------------------------------------------------- meta */

  usage: () => request<UsageState>("/usage"),

  /* ---------------------------------------------------------------- credits */

  creditPacks: () => request<CreditPacks>("/billing/packs"),

  createCreditOrder: (packId: string) =>
    request<CreditOrder>("/billing/orders", {
      method: "POST",
      body: JSON.stringify({ pack_id: packId }),
    }),

  confirmPayment: (body: PaymentConfirmation) =>
    request<{ credits_added: number; newly_granted: boolean; paid_credits: number }>(
      "/billing/verify",
      { method: "POST", body: JSON.stringify(body) },
    ),

  billingSummary: () => request<BillingSummary>("/billing/summary"),

  creditActivity: (kind: ActivityFilter, before?: number | null) =>
    request<{ items: CreditActivity[]; next: number | null }>(
      `/billing/activity?kind=${kind}&limit=20${before ? `&before=${before}` : ""}`,
    ),

  /** A plain link: the browser downloads it with the session cookie. */
  creditActivityCsvUrl: () => `${API_URL}/billing/activity.csv`,

  payments: () =>
    request<{ test_mode: boolean; items: PaymentRecord[] }>("/billing/payments"),

  pipelineMeta: () =>
    request<{
      pipeline: { node: string; label: string; detail: string }[];
      weights: Record<string, number>;
      thresholds: { buy: number; hold: number };
    }>("/meta/pipeline"),

  /* ---------------------------------------------------------------- auth */

  /** Resolves to null when signed out.
   *
   *  A 401 here is the correct answer to "who is this", not a failure, and letting it
   *  throw logs a console error on every page load for every visitor who is not signed
   *  in. */
  // /auth/session answers null for a visitor instead of a 401, which the browser
  // would otherwise log as an error on every page view.
  me: async (): Promise<CurrentUser | null> => {
    try {
      return await request<CurrentUser | null>("/auth/session");
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
      throw e;
    }
  },

  register: (email: string, password: string, name?: string) =>
    request<CurrentUser>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    }),

  /** Always resolves, whether or not the address has an account: telling the two
   *  apart would let anyone check which emails are registered. */
  forgotPassword: (email: string) =>
    request<null>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, password: string) =>
    request<unknown>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    }),

  login: async (email: string, password: string) => {
    const body = new URLSearchParams({ username: email, password });
    const res = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) {
      if (res.status === 400) {
        throw new ApiError(400, "That email and password do not match an account.");
      }
      throw await toError(res);
    }
  },

  logout: () => request<void>("/auth/logout", { method: "POST" }),

  /** A link, not a fetch. OAuth has to be a top-level browser navigation, and
   *  /authorize answers with JSON — following it shows a page of JSON. */
  googleAuthorizeUrl: () => `${API_URL}/auth/google/login`,
};

/** Server-side fetch for the landing page's showcase row.
 *
 *  Same contract as the memo below: runs during render, sends no cookies, never throws.
 *  An empty list is a landing page without a gallery, which is survivable; an exception
 *  is a 500 on the front door.
 */
export async function fetchShowcase(limit = 6): Promise<ShowcaseCard[]> {
  try {
    const res = await fetch(`${SERVER_API_URL}/public/showcase?limit=${limit}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return [];
    return (await res.json()) as ShowcaseCard[];
  } catch {
    return [];
  }
}

/** Server-side fetch of one completed analysis, for the landing page's live panel. */
export async function fetchAnalysis(id: string): Promise<AnalysisDetail | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/analyses/${id}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as AnalysisDetail;
  } catch {
    return null;
  }
}

/** Server-side fetch for the landing page's sample memo.
 *
 *  Kept separate from `api` because it runs during render, must not send cookies,
 *  and must never throw — a landing page that 500s because the backend is asleep
 *  is worse than one that shows the input on its own.
 */
export async function fetchSampleMemo(): Promise<AnalysisDetail | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/public/sample/memo`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as AnalysisDetail;
  } catch {
    return null;
  }
}
