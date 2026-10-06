/** One plain sentence per metric, for readers who do not speak finance.
 *
 *  Shown under each metric's name. The formula and the statement lines stay one click
 *  away in the derivation strip; this is only what the number means and which way is
 *  good.
 */
export const METRIC_HELP: Record<string, string> = {
  // Profitability
  gross_margin: "Share of each sales dollar left after the direct cost of making the product. Higher is better.",
  operating_margin: "Share of each sales dollar left after all day-to-day running costs. Higher is better.",
  net_margin: "Share of each sales dollar kept as final profit, after tax and interest. Higher is better.",
  ebitda_margin: "Operating profit before interest, tax and wear-and-tear on assets, as a share of sales. Higher is better.",
  fcf_margin: "Share of each sales dollar that turns into spare cash after investment. Higher is better.",
  roe: "Profit earned for every dollar shareholders have put in. Higher is better.",
  roa: "Profit earned for every dollar of things the company owns. Higher is better.",
  roic: "Profit earned on all the money invested in the business, from owners and lenders. Higher is better.",
  asset_turnover: "Sales generated for every dollar of assets. Higher means assets are used more efficiently.",
  equity_multiplier: "How much of the business is funded by borrowing rather than shareholders. Higher means more debt.",

  // Financial health
  current_ratio: "Short-term assets compared with bills due within a year. Above 1 means it can cover them.",
  quick_ratio: "Like the current ratio, but counting only cash and easily-sold assets. Above 1 is comfortable.",
  cash_ratio: "Cash alone compared with bills due within a year. Higher is safer.",
  debt_to_equity: "Debt compared with shareholders' money. Lower is safer.",
  net_debt_ebitda: "Years of operating profit needed to pay off debt after using its cash. Lower is safer; below 0 means more cash than debt.",
  interest_coverage: "How many times profit covers the interest on its debt. Higher is safer.",
  fcf_to_debt: "Spare cash each year compared with total debt. Higher means debt could be repaid faster.",
  altman_z: "A standard test of bankruptcy risk. Above 3 is considered safe, below 1.8 is a warning sign.",
  ccc: "Days between paying suppliers and collecting cash from customers. Lower is better; negative means customers pay first.",
  dso: "Average days customers take to pay. Lower is better.",
  dio: "Average days stock sits in the warehouse before being sold. Lower is better.",
  dpo: "Average days the company takes to pay its suppliers. Higher keeps more cash in hand.",

  // Growth
  rev_yoy: "How much sales grew compared with a year earlier.",
  eps_growth: "How much profit per share grew compared with a year earlier.",
  rev_cagr_3y: "Average yearly sales growth over the last three years.",
  rev_cagr_5y: "Average yearly sales growth over the last five years.",
  fcf_cagr_3y: "Average yearly growth in spare cash over the last three years.",
  rule_of_40: "Sales growth plus profit margin. Above 40% is a common sign of a healthy growing company.",
  reinvestment_rate: "Share of profit put back into the business to fuel growth.",
  growth_acceleration: "Whether sales growth is speeding up (positive) or slowing down (negative).",
  incremental_operating_margin: "How much of each extra sales dollar became extra operating profit this year.",

  // Valuation
  pe: "Share price divided by yearly profit per share: how many dollars you pay for each dollar of profit. Lower is cheaper.",
  peg: "The price/earnings figure adjusted for growth. Around 1 is often seen as fair; lower is cheaper.",
  ev_sales: "The whole company's value, including debt, compared with its yearly sales. Lower is cheaper.",
  ev_ebitda: "The whole company's value, including debt, compared with its yearly operating profit. Lower is cheaper.",
  fcf_yield: "Spare cash generated each year as a share of the company's market value. Higher is cheaper.",
  price_to_book: "Share price compared with the accounting value of what the company owns. Lower is cheaper.",
};
