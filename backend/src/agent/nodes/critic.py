"""Node 10: verify the memo before anyone reads it.

Two independent checks, deliberately not sharing a mechanism:

* a **model critic** reads the draft against the computed figures and reports what it
  thinks is wrong;
* a **Python verifier** regexes every percentage, multiple and currency figure out of
  the prose and matches it against computed state numerically.

The second exists because the first cannot be trusted to catch the failure it is most
likely to commit. Language models transpose digits — 31.5% becomes 35.1%, 25.8x becomes
28.5x — and a model re-reading its own draft is exactly the wrong instrument for
noticing that. Regex and arithmetic are the right instrument.

The Python verdict is authoritative: if it finds an unsupported figure, the memo goes
back for revision regardless of what the model critic said.
"""

from __future__ import annotations

import logging
import re

from ..models import get_router
from ..progress import node
from ..state import InvestmentMemo, MetricBlock
from ._shared import usage_from

log = logging.getLogger(__name__)

MAX_REVISIONS = 1

# 31.5%  |  25.8x  |  $1.2B / $431.00  |  1.57 (bare decimal)
PCT = re.compile(r"(-?\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*%")
MULT = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:x|×)\b", re.IGNORECASE)
CURRENCY = re.compile(r"\$\s?(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*([BMTK])?", re.IGNORECASE)
BARE = re.compile(r"(?<![\w.$])(-?\d+\.\d+)(?![\w%x×])")

SCALE = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}

# Small integers and years are prose, not claims about computed state.
IGNORE_BARE = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 100.0}

CRITIC_SYSTEM = """You are verifying a draft investment memo against the computed figures \
that produced it. You are not rewriting it and not judging the investment case.

Return JSON with exactly these keys:
{
  "numeric_claims": [{"claim": "<the sentence>", "value_stated": <number>, "matches_state": true|false}],
  "uncited_qualitative_claims": ["<sentence making a claim about the world with no [S#] tag>"],
  "hedging_score": <0.0 to 1.0, how much the draft equivocates instead of arguing>,
  "verdict": "pass" | "revise"
}

Check, in order:
1. Every number in the draft appears in the computed figures with the same value and unit.
2. Every claim about competition, management, regulation, demand, customers, products or \
litigation carries a [S#] tag that exists in the evidence list.
3. The memo argues for the rating it was given and does not quietly recommend something else.

Return "revise" if any number is wrong or any uncited claim about the world remains. \
Stylistic preferences are not grounds for revision."""


def collect_known_values(state: dict) -> dict[str, list[float]]:
    """Every number the memo is permitted to state, bucketed by unit."""
    buckets: dict[str, list[float]] = {"percent": [], "x": [], "currency": [], "ratio": [], "days": [], "score": []}

    for key in ("profitability", "liquidity", "growth", "peers"):
        block: MetricBlock | None = state.get(key)
        if block is None:
            continue
        for m in block.metrics.values():
            if m.value is not None:
                buckets.setdefault(m.unit, []).append(float(m.value))
            if m.peer_percentile is not None:
                buckets["percent"].append(float(m.peer_percentile))
            for h in m.history or []:
                if h.get("value") is not None:
                    buckets.setdefault(m.unit, []).append(float(h["value"]))
            # Raw statement inputs are quotable too.
            for v in (m.inputs or {}).values():
                if isinstance(v, int | float) and v is not None:
                    buckets["currency"].append(float(v))
                    buckets["ratio"].append(float(v))

    card = state.get("scorecard") or {}
    for v in (card.get("dimension_scores") or {}).values():
        if v is not None:
            buckets["score"].append(float(v))
            buckets["ratio"].append(float(v))
    if card.get("total") is not None:
        buckets["score"].append(float(card["total"]))
        buckets["ratio"].append(float(card["total"]))
    for v in (card.get("weights_applied") or {}).values():
        buckets["percent"].append(float(v))

    pt = state.get("price_target") or {}
    for k in ("low", "mid", "high"):
        if pt.get(k) is not None:
            buckets["currency"].append(float(pt[k]))
    if (pt.get("inputs") or {}).get("peer_median_ev_ebitda") is not None:
        buckets["x"].append(float(pt["inputs"]["peer_median_ev_ebitda"]))
    buckets["percent"].append(0.15)  # the stated +/-15% target band

    market = state.get("market") or {}
    for k in ("price", "market_cap", "shares_out", "fifty_two_week_high", "fifty_two_week_low"):
        if market.get(k) is not None:
            buckets["currency"].append(float(market[k]))

    peers_block: MetricBlock | None = state.get("peers")
    if peers_block is not None:
        for row in (peers_block.extras or {}).get("peer_rows", []):
            for v in row.values():
                if isinstance(v, int | float):
                    buckets["ratio"].append(float(v))
                    buckets["x"].append(float(v))
                    buckets["currency"].append(float(v))
        med = (peers_block.extras or {}).get("peer_median_ev_ebitda")
        if med is not None:
            buckets["x"].append(float(med))

    return buckets


def _matches(value: float, candidates: list[float], *, abs_tol: float, rel_tol: float) -> bool:
    for c in candidates:
        if abs(value - c) <= max(abs_tol, abs(c) * rel_tol):
            return True
    return False


def verify_numbers(text: str, known: dict[str, list[float]]) -> list[dict]:
    """Find figures in the prose that computed state does not support.

    Percentages are compared after converting to the fractional form the metrics use,
    which is also where a units error would show up: "31.5%" against a stored 0.315.
    """
    findings: list[dict] = []

    for raw in PCT.findall(text):
        stated = float(raw.replace(",", ""))
        as_fraction = stated / 100.0
        ok = _matches(as_fraction, known.get("percent", []), abs_tol=0.0015, rel_tol=0.02)
        # Growth and margin figures are sometimes quoted in points; allow the raw form
        # against ratio-unit values (a score of 7.5 written as "7.5%" is still wrong,
        # but "40%" against a Rule-of-40 score of 40 is not).
        if not ok:
            ok = _matches(stated, known.get("score", []) + known.get("days", []), abs_tol=0.06, rel_tol=0.01)
        if not ok:
            findings.append({"kind": "percent", "stated": stated, "text": raw + "%"})

    for raw in MULT.findall(text):
        stated = float(raw)
        pools = known.get("x", []) + known.get("ratio", [])
        if not _matches(stated, pools, abs_tol=0.02, rel_tol=0.02):
            findings.append({"kind": "multiple", "stated": stated, "text": raw + "x"})

    for raw, suffix in CURRENCY.findall(text):
        stated = float(raw.replace(",", ""))
        if suffix:
            stated *= SCALE[suffix.upper()]
        pools = known.get("currency", [])
        # Currency is quoted rounded ("$1.2B" for 1,234,567,890), so the tolerance is
        # proportional and generous.
        if not _matches(stated, pools, abs_tol=0.01, rel_tol=0.06):
            findings.append({"kind": "currency", "stated": stated, "text": f"${raw}{suffix or ''}"})

    for raw in BARE.findall(text):
        stated = float(raw)
        if stated in IGNORE_BARE or 1900 < stated < 2100:
            continue
        pools = (
            known.get("ratio", []) + known.get("x", []) + known.get("score", [])
            + known.get("days", []) + known.get("currency", [])
        )
        if not _matches(stated, pools, abs_tol=0.02, rel_tol=0.02):
            findings.append({"kind": "bare", "stated": stated, "text": raw})

    # De-duplicate: the same wrong figure repeated is one problem.
    seen: set[tuple] = set()
    unique = []
    for f in findings:
        key = (f["kind"], round(f["stated"], 6))
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique


def memo_text(m: InvestmentMemo) -> str:
    return " ".join(
        [
            m.thesis,
            *m.key_drivers,
            *m.key_risks,
            *m.what_would_change_our_mind,
            *m.data_caveats,
        ]
    )


@node("critic")
async def critic(state: dict) -> dict:
    m: InvestmentMemo | None = state.get("memo")
    if m is None:
        return {"critic_verdict": {"verdict": "pass", "reason": "no memo to verify"}}

    text = memo_text(m)
    known = collect_known_values(state)
    unsupported = verify_numbers(text, known)

    evidence = state.get("evidence") or []
    valid_labels = {e.label for e in evidence}
    bad_tags = sorted(
        {t for t in re.findall(r"\[S(\d{1,2})\]", text) if f"S{t}" not in valid_labels}
    )

    usage = usage_from(state)
    router = get_router()

    from .memo import render_evidence, render_figures, render_rating

    llm_verdict = await router.json_call(
        "critic",
        system=CRITIC_SYSTEM,
        user="\n".join(
            [
                "DRAFT MEMO:",
                m.model_dump_json(indent=2),
                "",
                "COMPUTED FIGURES:",
                render_figures(state),
                "",
                render_rating(state),
                "",
                "EVIDENCE LABELS AVAILABLE: " + (", ".join(sorted(valid_labels)) or "none"),
                "",
                render_evidence(evidence)[:6000],
            ]
        ),
        usage=usage,
        label="critic",
        fallback={
            "numeric_claims": [],
            "uncited_qualitative_claims": [],
            "hedging_score": 0.0,
            "verdict": "pass",
        },
    )

    # The Python check overrides the model's opinion in both directions: it can force a
    # revision the model waved through, and its "clean" result is what makes a pass
    # meaningful.
    python_verdict = "revise" if (unsupported or bad_tags) else "pass"
    model_verdict = llm_verdict.get("verdict", "pass")
    final = "revise" if python_verdict == "revise" or model_verdict == "revise" else "pass"

    revision = state.get("revision_count", 0)
    if revision >= MAX_REVISIONS:
        final = "pass"  # one revision only; shipping a flagged memo beats looping

    verdict = {
        "verdict": final,
        "python_verdict": python_verdict,
        "model_verdict": model_verdict,
        "numeric_claims": [
            {
                "claim": _sentence_containing(text, f["text"]),
                "value_stated": f["stated"],
                "matches_state": False,
                "kind": f["kind"],
            }
            for f in unsupported
        ]
        + [c for c in llm_verdict.get("numeric_claims", []) if isinstance(c, dict)][:10],
        "uncited_qualitative_claims": [
            c for c in llm_verdict.get("uncited_qualitative_claims", []) if isinstance(c, str)
        ][:10],
        "invalid_citation_tags": [f"S{t}" for t in bad_tags],
        "hedging_score": float(llm_verdict.get("hedging_score", 0.0) or 0.0),
        "unsupported_figures": unsupported,
        "figures_checked": _count_figures(text),
        "revision_count": revision,
        "capped": revision >= MAX_REVISIONS,
    }

    return {
        "critic_verdict": verdict,
        "revision_count": revision + (1 if final == "revise" else 0),
        "cost": usage.as_dict(),
        "trace": [
            {
                "node": "critic",
                "status": "verified",
                "verdict": final,
                "unsupported_figures": len(unsupported),
                "invalid_tags": len(bad_tags),
                "figures_checked": verdict["figures_checked"],
            }
        ],
    }


def _count_figures(text: str) -> int:
    return (
        len(PCT.findall(text))
        + len(MULT.findall(text))
        + len(CURRENCY.findall(text))
        + len(BARE.findall(text))
    )


def _sentence_containing(text: str, needle: str) -> str:
    for s in re.split(r"(?<=[.!?])\s+", text):
        if needle in s:
            return s[:240]
    return needle


def should_revise(state: dict) -> str:
    """Conditional edge. One revision, then ship."""
    verdict = state.get("critic_verdict") or {}
    if verdict.get("verdict") == "revise" and state.get("revision_count", 0) <= MAX_REVISIONS:
        return "memo"
    return "end"
