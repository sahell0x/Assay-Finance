"""Node 9: write the memo.

The model receives four things: the computed metric blocks, numbered evidence, the
scorecard *with the rating already decided*, and the data-quality report. Its job is to
argue the assigned rating, not to choose one. If it disagrees with the rating it is
instructed to record that in ``data_caveats``, where a reader can see the disagreement
rather than having it silently override the rubric.

Two validations run afterwards, both in Python:

* **citation enforcement** — sentences that make a qualitative claim without a valid
  ``[S#]`` tag are stripped, and the citation rate is recorded in the trace;
* **numeric verification** — every percentage and multiple in the prose is regexed out
  and matched against computed state. That happens in the critic node.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from ...analytics import scoring as sc
from ...data.fundamentals import Fundamentals
from ..models import UNTRUSTED_NOTICE, get_router, wrap_untrusted
from ..progress import node
from ..state import Evidence, InvestmentMemo
from ._shared import PLAIN_REMINDER, fmt, fmt_currency, usage_from

log = logging.getLogger(__name__)

_EMPTY_CAVEAT = re.compile(r"^no (data[- ]quality )?(issues|problems|caveats)( were)? recorded\.?$", re.I)

MEMO_SYSTEM = f"""You are a senior equity research analyst writing an investment memo for \
private investors who are not finance professionals.

{UNTRUSTED_NOTICE}

THE RATING IS ALREADY DECIDED. It was produced by a deterministic scoring rubric from \
the computed figures, before you were called. Your job is to write the strongest honest \
argument for that rating and to state its risks fairly. You must not change it, hedge \
it into meaninglessness, or imply a different conclusion. If, on the evidence in front \
of you, you believe the rating is wrong, say exactly that in `data_caveats` — that is \
where a disagreement belongs and it will be shown to the reader.

NUMBERS. Every figure you may use appears in the COMPUTED FIGURES section below. Do not \
calculate, derive, convert, annualise, round differently, or estimate any number that \
is not written there. Quote figures exactly as they are formatted. If a figure you want \
is not present, write the sentence without it.

CITATIONS. Any statement about competitive position, management, regulation, demand, \
customers, products, litigation, or anything else not visible in the computed figures \
MUST end with a source tag in square brackets, like [S3], naming the evidence item it \
comes from. Multiple tags are allowed: [S2][S7]. Sentences that are purely about the \
computed figures need no tag. Never invent a tag number that is not in the evidence list.

READER AND STYLE — this matters as much as accuracy. The reader is an intelligent \
private investor with NO finance training. Write in plain English, like a good \
newspaper explaining a company, not like an analyst writing for other analysts.
- Use at most TWO figures in any sentence. Pick the figures that matter most; the full \
table is shown elsewhere on the page, so you do not need to list every ratio.
- Lead with what a figure means, then give the figure: "The company keeps an unusually \
large share of its sales as profit" before the percentage, not a list of margins.
- Do not use an acronym or piece of jargon (EBITDA, CAGR, EV, ROIC, ROE, EPS, PEG, \
margin of safety, working capital, leverage, solvency, multiple, franchise) unless you \
explain it in plain words in the same sentence, the first time it appears. Prefer the \
everyday phrase: "profit", "sales", "debt", "spare cash", "average yearly growth", \
"how expensive the shares are compared with similar companies".
- Short sentences. Specific, declarative, no hedging, no throat-clearing.
- Explain meaning in words; never convert or restate a number in another form, \
because every figure is checked against the computed ones."""

# A sentence containing any of these is making a claim about the world rather than
# reporting a computed figure, so it needs a citation.
#
# Two lists, because the boundary rules differ: a stem like "compet" has to match
# "competition" and "competitor", so it must NOT be followed by \b (there is no word
# boundary inside a word) — a mistake that silently disables prefix markers and lets
# uncited claims through.
_STEMS = (
    "compet", "regulat", "litigat", "acquisi", "investigat", "announc", "expect",
    "guidanc", "guide", "partner", "launch", "strateg", "supplier", "customer",
    "subsidi", "legislat", "antitrust", "monopol",
)
_WORDS = (
    "market share", "management", "lawsuit", "demand", "supply", "product",
    "products", "merger", "contract", "contracts", "tariff", "tariffs", "sanction",
    "sanctions", "labour", "labor", "strike", "recall", "according to", "analyst",
    "analysts", "consensus", "plans", "intends", "brand", "pricing power",
    "headwind", "headwinds", "tailwind", "tailwinds", "backlog", "churn",
    "executive", "ceo", "cfo", "board", "union", "patent", "fda", "sec", "doj",
)
QUALITATIVE_MARKERS = re.compile(
    r"\b(?:" + "|".join(_STEMS) + r")|\b(?:" + "|".join(_WORDS) + r")\b",
    re.IGNORECASE,
)

CITATION_TAG = re.compile(r"\[S(\d{1,2})\]")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def enforce_citations(text: str, valid_labels: set[str]) -> tuple[str, dict]:
    """Strip qualitative sentences that carry no valid citation.

    Returns the cleaned text plus statistics. This runs in Python rather than being
    asked of the model, because a model that invents a fact will just as happily invent
    the tag that appears to support it.
    """
    sentences = split_sentences(text)
    kept: list[str] = []
    stripped: list[str] = []
    cited = 0
    needs_citation = 0

    for s in sentences:
        tags = CITATION_TAG.findall(s)
        requires = bool(QUALITATIVE_MARKERS.search(s))
        if requires:
            needs_citation += 1

        if not tags:
            if requires:
                stripped.append(s)
                continue
            kept.append(s)
            continue

        valid = [f"S{n}" for n in tags if f"S{n}" in valid_labels]
        if not valid:
            # Every tag is out of range: a fabricated citation is worse than none.
            if requires:
                stripped.append(s)
                continue
            kept.append(CITATION_TAG.sub("", s).strip())
            continue

        # Drop only the invented tags, keep the real ones.
        cleaned = CITATION_TAG.sub(
            lambda m: m.group(0) if f"S{m.group(1)}" in valid_labels else "", s
        ).strip()
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        kept.append(cleaned)
        cited += 1

    stats = {
        "sentences": len(sentences),
        "kept": len(kept),
        "stripped": len(stripped),
        "stripped_text": stripped[:6],
        "needing_citation": needs_citation,
        "cited": cited,
        "citation_rate": round(cited / needs_citation, 3) if needs_citation else 1.0,
        "strip_rate": round(len(stripped) / len(sentences), 3) if sentences else 0.0,
    }
    return " ".join(kept), stats


def cited_labels(memo: InvestmentMemo) -> list[str]:
    blob = " ".join(
        [memo.thesis, *memo.key_drivers, *memo.key_risks, *memo.what_would_change_our_mind]
    )
    return sorted({f"S{n}" for n in CITATION_TAG.findall(blob)}, key=lambda s: int(s[1:]))


# --------------------------------------------------------------------------- prompting


def render_figures(state: dict) -> str:
    """The complete set of numbers the model is permitted to use, pre-formatted."""
    f = Fundamentals.from_dict(state["facts"])
    lines: list[str] = []

    market = state.get("market") or {}
    lines.append(f"Company: {f.name} ({f.ticker})")
    lines.append(f"Sector: {f.sector or 'not reported'} | Industry: {f.industry or 'not reported'}")
    if market.get("price") is not None:
        lines.append(f"Share price: ${market['price']:,.2f}")
    if market.get("market_cap") is not None:
        lines.append(f"Market capitalisation: {fmt_currency(market['market_cap'])}")
    lines.append(f"Reporting basis: {f.periods[0] if f.periods else 'unknown'}")
    lines.append("")

    for key, title in (
        ("profitability", "PROFITABILITY"),
        ("liquidity", "LIQUIDITY, LEVERAGE AND SOLVENCY"),
        ("growth", "GROWTH"),
        ("peers", "VALUATION AND PEERS"),
    ):
        block = state.get(key)
        if block is None:
            continue
        lines.append(f"--- {title} (dimension score {block.score:.1f}/10) ---")
        for m in block.metrics.values():
            row = f"  {m.label}: {fmt(m)}"
            if m.peer_percentile is not None:
                row += f"  [peer percentile {m.peer_percentile * 100:.0f}]"
            if m.flag:
                row += f"  [{m.flag}]"
            lines.append(row)
        if block.narrative:
            lines.append(f"  Section reading: {block.narrative}")
        for w in block.warnings:
            lines.append(f"  Caveat: {w}")
        lines.append("")

    return "\n".join(lines)


def render_evidence(evidence: list[Evidence]) -> str:
    if not evidence:
        return (
            "No source documents were retrieved for this company. Every qualitative "
            "claim would therefore be uncitable — confine the memo to the computed "
            "figures and note the absence of source material in data_caveats."
        )
    out = ["Numbered evidence. Cite by label, e.g. [S1]."]
    for e in evidence:
        header = f"[{e.label}] {e.source_type}"
        if e.section:
            header += f" — {e.section}"
        if e.published:
            header += f" — {e.published}"
        if e.title:
            header += f" — {e.title}"
        out.append(header)
        out.append(wrap_untrusted(e.label, e.text[:1400]))
        out.append("")
    return "\n".join(out)


def render_rating(state: dict) -> str:
    card = state.get("scorecard") or {}
    pt = state.get("price_target") or {}
    lines = [
        f"RATING (already decided, argue for it): {card.get('rating')}",
        f"Conviction: {card.get('conviction')}",
        f"Composite score: {card.get('total')} out of 10 "
        f"(BUY at {sc.BUY_THRESHOLD}+, HOLD at {sc.HOLD_THRESHOLD}+, SELL below)",
        "Dimension scores: "
        + ", ".join(
            f"{k} {v}" for k, v in (card.get("dimension_scores") or {}).items() if v is not None
        ),
        "Weights applied: "
        + ", ".join(f"{k} {v:.0%}" for k, v in (card.get("weights_applied") or {}).items()),
    ]
    if card.get("dimensions_unavailable"):
        lines.append("Unavailable and reweighted: " + ", ".join(card["dimensions_unavailable"]))
    if pt.get("available"):
        lines.append(
            f"Price target band: ${pt['low']:,.2f} to ${pt['high']:,.2f} "
            f"(midpoint ${pt['mid']:,.2f}). Method: {pt['method']}"
        )
    else:
        lines.append(
            f"Price target: not available. {pt.get('reason', '')} "
            f"Set price_target_low and price_target_high to null and say so in valuation_method."
        )
    return "\n".join(lines)


def _fallback_memo(state: dict) -> InvestmentMemo:
    """Deterministic memo used when no model is reachable.

    It is assembled entirely from computed state, so it is accurate; it just is not
    written. The caveat list says so plainly.
    """
    f = Fundamentals.from_dict(state["facts"])
    card = state.get("scorecard") or {}
    pt = state.get("price_target") or {}
    scores = {k: v for k, v in (card.get("dimension_scores") or {}).items() if v is not None}
    strongest = max(scores, key=scores.get) if scores else None
    weakest = min(scores, key=scores.get) if scores else None

    drivers = []
    risks = []
    for block in (
        state.get("profitability"),
        state.get("growth"),
        state.get("peers"),
        state.get("liquidity"),
    ):
        if block is None:
            continue
        for m in block.metrics.values():
            if m.value is None:
                continue
            line = f"{m.label} of {fmt(m)} ({m.period})"
            if m.flag == "strong" and len(drivers) < 5:
                drivers.append(line)
            elif m.flag == "weak" and len(risks) < 5:
                risks.append(line)

    while len(drivers) < 3:
        drivers.append(f"{strongest or 'Overall'} scores {scores.get(strongest, 0):.1f} out of 10 on the rubric")
    while len(risks) < 3:
        risks.append(f"{weakest or 'Overall'} scores {scores.get(weakest, 0):.1f} out of 10 on the rubric")

    return InvestmentMemo(
        ticker=f.ticker,
        as_of=date.today().isoformat(),
        recommendation=card.get("rating", "HOLD"),
        conviction=card.get("conviction", "low"),
        thesis=(
            f"{f.name} scores {card.get('total')} out of 10 on the composite rubric, "
            f"which places it in the {card.get('rating')} band. The strongest dimension is "
            f"{strongest or 'none'} and the weakest is {weakest or 'none'}. This summary was "
            f"assembled directly from the computed figures rather than written, because no "
            f"language model was reachable for this run."
        ),
        price_target_low=pt.get("low"),
        price_target_high=pt.get("high"),
        valuation_method=pt.get("method", "Not available"),
        key_drivers=drivers[:5],
        key_risks=risks[:5],
        what_would_change_our_mind=[
            "A material change in the dimension that currently scores lowest",
            "A revision to the reported figures in the next quarterly filing",
        ],
        data_caveats=[
            "This memo's prose was generated deterministically from computed state "
            "because no language model was available. All figures are nonetheless "
            "computed from the filings and are unaffected.",
        ],
        cited_sources=[],
    )


@node("memo")
async def memo(state: dict) -> dict:
    f = Fundamentals.from_dict(state["facts"])
    evidence: list[Evidence] = state.get("evidence") or []
    valid_labels = {e.label for e in evidence}
    revision = state.get("revision_count", 0)
    usage = usage_from(state)
    router = get_router()

    prompt_parts = [
        render_rating(state),
        "",
        "COMPUTED FIGURES — the only numbers you may use:",
        render_figures(state),
        "",
        "EVIDENCE:",
        render_evidence(evidence),
        "",
        "DATA QUALITY:",
        *[f"- {w}" for w in (state.get("data_quality", {}).get("warnings") or ["No issues recorded."])],
    ]

    if revision:
        verdict = state.get("critic_verdict") or {}
        prompt_parts += [
            "",
            "REVISION. Your previous draft was rejected by a verification pass. Fix "
            "exactly these problems and change nothing else:",
        ]
        for c in verdict.get("numeric_claims", []):
            if not c.get("matches_state", True):
                prompt_parts.append(
                    f"- The figure {c.get('value_stated')} in \"{c.get('claim', '')[:120]}\" "
                    f"does not match computed state. Use the value from COMPUTED FIGURES or drop the sentence."
                )
        for c in verdict.get("uncited_qualitative_claims", [])[:8]:
            prompt_parts.append(f"- This claim has no valid citation and must be cited or removed: \"{c[:160]}\"")
        if verdict.get("hedging_score", 0) > 0.5:
            prompt_parts.append("- The draft hedges excessively. Make the argument directly.")

    prompt_parts += ["", PLAIN_REMINDER]

    result = await router.structured(
        "memo",
        system=MEMO_SYSTEM,
        user="\n".join(prompt_parts),
        schema=InvestmentMemo,
        usage=usage,
        label="memo",
        fallback=_fallback_memo(state),
        max_tokens=2500,
    )

    # --- enforce citations in Python ---------------------------------------
    thesis, thesis_stats = enforce_citations(result.thesis, valid_labels)
    drivers, driver_stats = _clean_list(result.key_drivers, valid_labels)
    risks, risk_stats = _clean_list(result.key_risks, valid_labels)
    changes, _ = _clean_list(result.what_would_change_our_mind, valid_labels)

    overall_strip = _combined_strip_rate([thesis_stats, driver_stats, risk_stats])

    # One stricter retry when the model is citing badly enough that the memo is being
    # gutted. Beyond that, ship what survived rather than burning more tokens.
    if overall_strip > 0.40 and not revision and not router.offline and evidence:
        log.info("citation strip rate %.2f — retrying with a stricter prompt", overall_strip)
        stricter = (
            "\n\nSTRICTER PASS: your previous attempt had too many uncited claims and "
            "they were removed. Every sentence that is not purely about the computed "
            "figures must end with a valid [S#] tag from the evidence list. If you "
            "cannot cite a claim, do not make it."
        )
        result = await router.structured(
            "memo",
            system=MEMO_SYSTEM,
            user="\n".join(prompt_parts) + stricter,
            schema=InvestmentMemo,
            usage=usage,
            label="memo:strict-retry",
            fallback=result,
            max_tokens=2500,
        )
        thesis, thesis_stats = enforce_citations(result.thesis, valid_labels)
        drivers, driver_stats = _clean_list(result.key_drivers, valid_labels)
        risks, risk_stats = _clean_list(result.key_risks, valid_labels)
        changes, _ = _clean_list(result.what_would_change_our_mind, valid_labels)
        overall_strip = _combined_strip_rate([thesis_stats, driver_stats, risk_stats])

    card = state.get("scorecard") or {}
    pt = state.get("price_target") or {}

    # The rating and the price target come from the rubric, not the draft. Overwriting
    # them here means a model that ignored the instruction cannot change the outcome.
    final = InvestmentMemo(
        ticker=f.ticker,
        as_of=date.today().isoformat(),
        recommendation=card.get("rating", "HOLD"),
        conviction=card.get("conviction", "low"),
        thesis=thesis or result.thesis,
        price_target_low=pt.get("low") if pt.get("available") else None,
        price_target_high=pt.get("high") if pt.get("available") else None,
        valuation_method=pt.get("method", result.valuation_method),
        key_drivers=_pad(drivers, result.key_drivers, 3),
        key_risks=_pad(risks, result.key_risks, 3),
        what_would_change_our_mind=changes or result.what_would_change_our_mind,
        data_caveats=result.data_caveats,
        cited_sources=[],
    )
    final.cited_sources = cited_labels(final)

    # The prompt's own "No issues recorded." placeholder sometimes comes back as a caveat.
    # It tells a reader nothing, and a note saying there is nothing to note is noise.
    final.data_caveats = [c for c in final.data_caveats if not _EMPTY_CAVEAT.match(c.strip())]

    # If the provider faltered at any point in the run, say so in the memo itself
    # rather than only in the trace. A reader looking at prose that reads thinly
    # deserves to know it was assembled from computed state after the model became
    # unreachable — and to know that the figures are unaffected, because they are.
    if router.degraded:
        log.warning("memo assembled in degraded mode: %s", router.degraded)
        note = (
            "Some written explanations could not be generated for this analysis, so "
            "shorter automatic text was used in places. Every number is unaffected."
        )
        if note not in final.data_caveats:
            final.data_caveats = [note, *final.data_caveats]

    stats = {
        "citation_rate": thesis_stats["citation_rate"],
        "strip_rate": round(overall_strip, 3),
        "sentences_stripped": thesis_stats["stripped"] + driver_stats["stripped"] + risk_stats["stripped"],
        "evidence_available": len(evidence),
        "sources_cited": len(final.cited_sources),
        "revision": revision,
    }

    return {
        "memo": final,
        "cost": usage.as_dict(),
        "trace": [{"node": "memo", "status": "citations", **stats}],
    }


def _clean_list(items: list[str], valid: set[str]) -> tuple[list[str], dict]:
    kept: list[str] = []
    total_stripped = 0
    total_sentences = 0
    cited = 0
    needing = 0
    for item in items:
        cleaned, st = enforce_citations(item, valid)
        total_stripped += st["stripped"]
        total_sentences += st["sentences"]
        cited += st["cited"]
        needing += st["needing_citation"]
        # A claim stripped for want of a source can leave its tags behind as an item of
        # their own ("[S2]"). A bullet with no words in it is not a finding.
        if cleaned and CITATION_TAG.sub("", cleaned).strip(" .;,:-"):
            kept.append(cleaned)
    return kept, {
        "stripped": total_stripped,
        "sentences": total_sentences,
        "cited": cited,
        "needing_citation": needing,
        "citation_rate": round(cited / needing, 3) if needing else 1.0,
        "strip_rate": round(total_stripped / total_sentences, 3) if total_sentences else 0.0,
    }


def _combined_strip_rate(stats_list: list[dict]) -> float:
    total = sum(s["sentences"] for s in stats_list)
    stripped = sum(s["stripped"] for s in stats_list)
    return stripped / total if total else 0.0


def _pad(cleaned: list[str], original: list[str], minimum: int) -> list[str]:
    """The schema requires at least three drivers and risks. If citation enforcement
    took the list below that, restore the least-bad originals with their invalid tags
    removed rather than emitting an invalid memo."""
    out = list(cleaned)
    if len(out) >= minimum:
        return out[:5]
    for item in original:
        stripped = CITATION_TAG.sub("", item).strip()
        if stripped and stripped not in out:
            out.append(stripped)
        if len(out) >= minimum:
            break
    while len(out) < minimum:
        out.append("Not enough source material was available to support a further point.")
    return out[:5]
