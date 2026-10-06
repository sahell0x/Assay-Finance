"""Helpers common to the analysis nodes.

Chief among them is :func:`narrate`, which is the only way a node asks a model for
prose. It hands over a rendered table of already-computed values and forbids arithmetic.
That constraint is the whole architecture in one function: the model interprets, it does
not calculate.
"""

from __future__ import annotations

from ..models import Usage, get_router
from ..state import MetricValue

NARRATIVE_SYSTEM = """You are an equity research analyst writing one short section of a \
research note for private investors who are not finance professionals.

Hard rules:
1. Every number you may use is given to you below, already computed. Do NOT calculate, \
derive, infer, restate in different units, or estimate any figure that is not in the \
table. If a value is marked "not available", say it is not available — never guess it.
2. Quote figures exactly as formatted in the table.
3. Write 3-5 sentences of plain, specific prose. No headings, no bullet points, no \
preamble, no bold.
4. Say what the numbers mean for the business: what is driving them, what the trend \
implies, where the weakness is. Avoid hedging language and avoid restating the table.
5. Never state or imply a buy, sell, or hold recommendation. That decision is made \
elsewhere.
6. If a metric is flagged unreliable, say why in one clause rather than using it.
7. The reader has NO finance training. Write in plain English, like a good newspaper. \
Use at most TWO figures per sentence and pick only the figures that matter; the full \
table is shown right below your text. Say what a figure means before giving it. Do not \
use jargon or acronyms (EBITDA, CAGR, liquidity, leverage, solvency, working capital, \
Altman Z-score) unless you explain them in plain words in the same sentence. Explain \
meaning in words, never by converting or restating a figure in another form."""


# Repeated at the end of every request. Put only in the system prompt, the instruction
# lost to the long table of figures that comes after it and the prose stayed dense.
PLAIN_REMINDER = (
    "Before you write: the reader has no finance training. Use at most two figures per "
    "sentence, say what each one means in everyday words, and explain any jargon or "
    "acronym in the same sentence. Short sentences. Do not list ratios."
)


def fmt(m: MetricValue) -> str:
    """Render a metric the way the interface will, so prose and screen agree."""
    if m.value is None:
        reason = f" ({m.note})" if m.note else ""
        return f"not available{reason}"
    v = m.value
    if m.unit == "percent":
        return f"{v * 100:.1f}%"
    if m.unit == "days":
        return f"{v:.0f} days"
    if m.unit == "x":
        return f"{v:.2f}x"
    if m.unit == "currency":
        return fmt_currency(v)
    if m.unit == "score":
        return f"{v:.1f}/10"
    return f"{v:.2f}"


def fmt_currency(v: float) -> str:
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e12:
        return f"{sign}${a / 1e12:.2f}T"
    if a >= 1e9:
        return f"{sign}${a / 1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:.1f}M"
    return f"{sign}${a:,.0f}"


def metrics_table(metrics: dict[str, MetricValue]) -> str:
    """The value table handed to the model. Formatted values only — no raw floats, so
    there is nothing to do arithmetic on even if the model were inclined to."""
    lines = []
    for m in metrics.values():
        parts = [f"- {m.label or m.name}: {fmt(m)}"]
        if m.peer_percentile is not None:
            parts.append(f"peer percentile {m.peer_percentile * 100:.0f}")
        if m.yoy_change is not None and m.value is not None:
            direction = "up" if m.yoy_change >= 0 else "down"
            parts.append(f"{direction} {abs(m.yoy_change) * 100:.1f} pts year over year")
        if m.flag:
            parts.append(f"flag: {m.flag}")
        lines.append(" — ".join(parts))
    return "\n".join(lines)


async def narrate(
    *,
    company: str,
    section: str,
    metrics: dict[str, MetricValue],
    extra_context: str = "",
    warnings: list[str] | None = None,
    usage: Usage,
) -> str:
    router = get_router()
    body = [
        f"Company: {company}",
        f"Section: {section}",
        "",
        "Computed values (the only numbers you may use):",
        metrics_table(metrics),
    ]
    if extra_context:
        body += ["", extra_context]
    if warnings:
        body += ["", "Data limitations to acknowledge if relevant:"] + [
            f"- {w}" for w in warnings
        ]
    body += ["", PLAIN_REMINDER]
    return await router.complete(
        "narrative",
        system=NARRATIVE_SYSTEM,
        user="\n".join(body),
        usage=usage,
        label=f"narrative:{section}",
        # Reasoning models spend part of this budget thinking before they write, and at
        # 400 a section occasionally ran out and fell back to placeholder text.
        max_tokens=1200,
        temperature=0.3,
    )


def usage_from(state: dict) -> Usage:
    """One Usage object per run, threaded through state as a plain dict."""
    existing = state.get("cost")
    u = Usage()
    if existing:
        u.tokens_in = existing.get("tokens_in", 0)
        u.tokens_out = existing.get("tokens_out", 0)
        u.cost_usd = existing.get("cost_usd", 0.0)
        u.calls = list(existing.get("calls", []))
    return u


def history_for(facts: dict, field: str, periods: list[str], compute) -> list[dict]:
    """Per-period series for the charts, newest-first, holes preserved as nulls."""
    out = []
    for p in periods:
        row = facts.get(p)
        if row is None:
            continue
        out.append({"period": p, "value": compute(row)})
    return out


def is_financial(sector: str) -> bool:
    return (sector or "").strip().lower() in {
        "financial services",
        "financials",
        "financial",
    }


def is_software(sector: str, industry: str) -> bool:
    blob = f"{sector} {industry}".lower()
    return "software" in blob or "information technology services" in blob
