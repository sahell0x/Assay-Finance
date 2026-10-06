/** Shapes returned by the backend. Kept in one file so a schema change breaks
 *  compilation somewhere obvious rather than at runtime in a chart. */

export type Rating = "BUY" | "HOLD" | "SELL";
export type Conviction = "low" | "medium" | "high";
export type Flag = "strong" | "neutral" | "weak" | "unreliable";
export type Unit = "ratio" | "percent" | "currency" | "days" | "x" | "score";

export interface MetricValue {
  name: string;
  label?: string | null;
  value: number | null;
  unit: Unit;
  period: string;
  /** The expression that produced the value. Shown verbatim, in mono. */
  formula: string;
  /** The statement lines that fed the formula. The audit trail. */
  inputs: Record<string, number | null>;
  peer_percentile?: number | null;
  yoy_change?: number | null;
  flag?: Flag | null;
  /** Why the value is unavailable, when it is. Never empty for a null value. */
  note?: string | null;
  history?: { period: string; value: number | null }[] | null;
}

export interface MetricBlock {
  dimension: "profitability" | "liquidity" | "growth" | "peers";
  metrics: Record<string, MetricValue>;
  /** Display order. Postgres reorders JSONB keys, so object order is not meaningful. */
  order?: string[];
  narrative: string;
  score: number;
  warnings: string[];
  extras: Record<string, unknown>;
}

export interface Scorecard {
  dimension_scores: Record<string, number | null>;
  weights_applied: Record<string, number>;
  weights_requested?: Record<string, number>;
  dimensions_unavailable: string[];
  total: number | null;
  rating: Rating;
  conviction: Conviction;
  thresholds: { buy: number; hold: number };
  distance_to_edge: number | null;
  coverage: number;
  detail?: Record<string, unknown>;
  price_target?: PriceTarget;
  narrative_by_dimension?: Record<string, string>;
}

export interface PriceTarget {
  low: number | null;
  mid?: number | null;
  high: number | null;
  method: string;
  available: boolean;
  reason?: string;
  implied_move?: number | null;
  stretched?: boolean;
  caveat?: string | null;
  inputs?: Record<string, number | null>;
}

export interface Memo {
  ticker: string;
  as_of: string;
  recommendation: Rating;
  conviction: Conviction;
  thesis: string;
  price_target_low: number | null;
  price_target_high: number | null;
  valuation_method: string;
  key_drivers: string[];
  key_risks: string[];
  what_would_change_our_mind: string[];
  data_caveats: string[];
  cited_sources: string[];
}

export interface Evidence {
  label: string;
  source_type: string;
  section?: string | null;
  title?: string | null;
  url?: string | null;
  published?: string | null;
  text: string;
  relevance?: number | null;
}

export interface PipelineStep {
  node: string;
  label: string;
  detail: string;
}

export interface NodeEvent {
  node: string;
  status: "pending" | "start" | "ok" | "error" | "skipped";
  duration_ms?: number | null;
  detail?: Record<string, unknown> | null;
  at?: string | null;
}

export interface DataQuality {
  coverage: number;
  annual_periods: number;
  has_ttm: boolean;
  missing_critical: string[];
  missing_important: string[];
  warnings: string[];
  usable: boolean;
  sector_flags?: Record<string, boolean>;
}

export interface Blocks {
  profitability?: MetricBlock | null;
  liquidity?: MetricBlock | null;
  growth?: MetricBlock | null;
  peers?: MetricBlock | null;
  retrieval?: RetrievalStats;
  critic?: CriticVerdict;
  market?: Market;
  facts?: Record<string, unknown>;
  warnings?: string[];
}

export interface RetrievalStats {
  queries_issued: number;
  queries: { q: string; theme: string; conditional: boolean }[];
  conditional_queries: { q: string; theme: string; because?: string }[];
  candidates: number;
  selected: number;
  corpus_size: number;
  indexed_on_demand: boolean;
  by_source: Record<string, number>;
  sentiment_rationale?: string;
  themes?: string[];
}

export interface CriticVerdict {
  verdict: "pass" | "revise";
  python_verdict?: string;
  model_verdict?: string;
  unsupported_figures?: { kind: string; stated: number; text: string }[];
  invalid_citation_tags?: string[];
  figures_checked?: number;
  hedging_score?: number;
  capped?: boolean;
}

export interface Market {
  price?: number | null;
  market_cap?: number | null;
  shares_out?: number | null;
  currency?: string;
  name?: string;
  sector?: string;
  industry?: string;
  fifty_two_week_high?: number | null;
  fifty_two_week_low?: number | null;
}

export interface AnalysisDetail {
  id: string;
  ticker: string;
  status: "queued" | "running" | "complete" | "failed";
  current_node?: string | null;
  peer_tickers?: string[] | null;
  weights?: Record<string, number> | null;
  scorecard?: Scorecard | null;
  memo?: Memo | null;
  blocks?: Blocks | null;
  data_quality?: DataQuality | null;
  evidence: Evidence[];
  events: NodeEvent[];
  pipeline: PipelineStep[];
  cached: boolean;
  cached_at?: string | null;
  public_slug?: string | null;
  error?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  owned: boolean;
}

export interface AnalysisSummary {
  id: string;
  ticker: string;
  status: string;
  rating?: Rating | null;
  conviction?: Conviction | null;
  total_score?: number | null;
  created_at?: string | null;
  completed_at?: string | null;
  cached: boolean;
  error?: string | null;
}

/** One pre-computed company on the landing page.
 *
 *  A summary is not enough for a card someone decides to click: it needs the company's
 *  name, what it trades at, and the dimension scores that draw the bar rail. */
export interface ShowcaseCard {
  id: string;
  ticker: string;
  name?: string | null;
  sector?: string | null;
  rating?: Rating | null;
  conviction?: Conviction | null;
  total_score?: number | null;
  dimension_scores: Record<string, number | null>;
  price?: number | null;
  currency?: string | null;
  market_cap?: number | null;
  thesis?: string | null;
  completed_at?: string | null;
}

export interface AnalysisAccepted {
  id: string;
  status: string;
  ticker: string;
  cached: boolean;
  cached_at?: string | null;
  stream_url: string;
  poll_url: string;
  budget?: BudgetState | null;
  quota?: UsageState | null;
}

/** Only whether new analyses are paused for today. The spend figures stay server-side. */
export interface BudgetState {
  exhausted: boolean;
}

export interface UsageState {
  scope: "anon" | "free" | "ip";
  /** Free credits used, and the free allowance (one-time either way). */
  used: number;
  limit: number;
  free_remaining: number;
  /** Bought credits. Always 0 for anonymous visitors. */
  paid_credits: number;
  /** Everything that can still be run: free credits left plus bought ones. */
  remaining: number;
  exhausted: boolean;
  authenticated: boolean;
  /** Free credits a new account gets, once. */
  account_free_credits: number;
  payments_enabled: boolean;
  /** Signed in, payments on, and not at the test-mode purchase limit. */
  can_buy: boolean;
  budget: BudgetState;
  signup_benefits: string[];
}

export interface CreditPack {
  id: string;
  name: string;
  credits: number;
  price_paise: number;
  currency: string;
  per_credit_paise: number;
  popular: boolean;
}

/** How much of the test-mode purchase limit an account has used. */
export interface TestLimits {
  max_purchases: number;
  max_credits: number;
  purchases_used: number;
  credits_bought: number;
  purchases_left: number;
  credits_left: number;
}

export interface CreditPacks {
  enabled: boolean;
  /** Razorpay test keys: the flow is real but no money moves. */
  test_mode: boolean;
  currency: string;
  packs: CreditPack[];
  /** Set when signed in and in test mode. */
  limits: TestLimits | null;
}

export interface CreditOrder {
  key_id: string;
  order_id: string;
  amount: number;
  currency: string;
  pack: CreditPack;
  name: string;
  prefill: { email: string; name: string };
  test_mode: boolean;
}

export interface PaymentConfirmation {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

/** One credit movement. Free credits read -1 / +1 like bought ones. */
export interface CreditActivity {
  id: number;
  kind: "purchase" | "spend" | "refund" | "free_spend" | "free_refund";
  source: "free" | "bought";
  delta: number;
  balance_after: number;
  created_at: string;
  ticker: string | null;
  analysis_id: string | null;
  pack_name: string | null;
  amount_paise: number | null;
  currency: string | null;
}

export type ActivityFilter = "all" | "usage" | "purchases";

export interface BillingSummary {
  credits_used: number;
  free_used: number;
  free_total: number;
  bought_used: number;
  credits_bought: number;
  paid_balance: number;
  purchases: number;
  amount_spent_paise: number;
  refunds: number;
  currency: string;
  daily: { date: string; free: number; bought: number }[];
}

export interface PaymentRecord {
  id: string;
  created_at: string;
  paid_at: string | null;
  pack_name: string;
  credits: number;
  amount_paise: number;
  currency: string;
  status: "paid" | "pending" | "abandoned" | "over_limit" | "refunded";
  order_id: string | null;
  payment_id: string | null;
}

export interface TickerSuggestion {
  ticker: string;
  name: string;
  exchange?: string | null;
  sector?: string | null;
}

export interface TickerResolution {
  matches: TickerSuggestion[];
  /** Set when the query names a well-known company that is not publicly traded. */
  private_company?: string | null;
}

export interface WatchlistEntry {
  ticker: string;
  added_at?: string | null;
  name?: string | null;
  rating?: Rating | null;
  total_score?: number | null;
  analysis_id?: string | null;
  last_run?: string | null;
}

export interface HistoryPoint {
  analysis_id: string;
  date: string;
  total: number | null;
  rating: Rating | null;
  dimension_scores?: Record<string, number | null> | null;
}

export interface CompareColumn {
  ticker: string;
  available: boolean;
  analysis_id?: string;
  completed_at?: string | null;
  rating?: Rating;
  conviction?: Conviction;
  total?: number | null;
  dimension_scores?: Record<string, number | null>;
  price_target?: PriceTarget;
  thesis?: string;
  key_risks?: string[];
}

export interface CurrentUser {
  id: string;
  email: string;
  name?: string | null;
  image_url?: string | null;
  plan: string;
  is_active: boolean;
}

/* ------------------------------------------------------------------ scenarios */

/** One thing the reader can move. Ranges come from the rubric's own anchor table, so a
 *  slider stops where the metric stops being scored differently. */
export interface ScenarioLever {
  name: string;
  label: string;
  dimension: string;
  unit: "pct" | "x" | "ratio" | "score" | "currency";
  value: number;
  min: number;
  max: number;
  step: number;
  higher_is_better: boolean;
}

/** One single-metric route to a different rating, or the statement that there is none.
 *  `reachable: false` is the common answer and is shown rather than filtered. */
export interface ScenarioPath {
  lever: string;
  label: string;
  dimension: string;
  unit: ScenarioLever["unit"];
  from: number;
  to: number | null;
  delta: number | null;
  effort: number | null;
  reachable: boolean;
  resulting_total: number | null;
  higher_is_better: boolean;
}

export interface ScenarioSetup {
  ticker: string;
  baseline: {
    total: number | null;
    rating: Rating;
    conviction: Conviction;
    distance_to_edge: number | null;
    dimension_scores: Record<string, number | null>;
    weights_applied: Record<string, number>;
    price_target?: PriceTarget | null;
  };
  thresholds: { buy: number; hold: number };
  levers: ScenarioLever[];
  target_rating: Rating;
  paths: ScenarioPath[];
}

export interface PriceScenario {
  price: number;
  baseline_price: number;
  move: number;
  factor: number;
  ev_factor: number;
}

/** A recomputed scorecard. Deliberately the same shape a real one has, so every
 *  component that renders the stored card renders a scenario unchanged. */
export interface ScenarioResult extends Scorecard {
  overridden: string[];
  price_scenario: PriceScenario | null;
  baseline: { total: number | null; rating: Rating; conviction: Conviction };
}

export const DIMENSIONS = [
  "profitability",
  "financial_health",
  "growth",
  "valuation",
  "sentiment",
] as const;

export const DIMENSION_LABELS: Record<string, string> = {
  profitability: "Profitability",
  financial_health: "Financial health",
  growth: "Growth",
  valuation: "Valuation",
  sentiment: "Sentiment",
};
