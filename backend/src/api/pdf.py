"""Memo as PDF.

reportlab rather than a headless browser: the memo is a text document with a handful of
tables, and shipping Chromium to render it would multiply the image size and the memory
ceiling for no gain. The typography follows the same rules as the interface — a serif
for the prose that gets read, tabular figures for anything in a column.
"""

from __future__ import annotations

import io
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# The site's palette: ink for text, and green / amber / red only for a verdict.
INK = colors.HexColor("#13201A")
MUTED = colors.HexColor("#56645E")
RULE = colors.HexColor("#D9E0DC")
ACCENT = colors.HexColor("#2563EB")
RATING_COLOURS = {
    "BUY": colors.HexColor("#16774A"),
    "HOLD": colors.HexColor("#975F00"),
    "SELL": colors.HexColor("#B3261E"),
}


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="Helvetica", fontSize=20,
            leading=24, textColor=INK, alignment=TA_LEFT, spaceAfter=2,
        ),
        "sub": ParagraphStyle(
            "sub", parent=base["Normal"], fontName="Helvetica", fontSize=9.5,
            leading=13, textColor=MUTED, spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11,
            leading=14, textColor=INK, spaceBefore=14, spaceAfter=5,
        ),
        # Serif for sustained reading, matching the interface's memo body.
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontName="Times-Roman", fontSize=10.5,
            leading=17, textColor=INK, spaceAfter=8,
        ),
        "item": ParagraphStyle(
            "item", parent=base["Normal"], fontName="Times-Roman", fontSize=10,
            leading=15.5, textColor=INK,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"], fontName="Helvetica", fontSize=8,
            leading=11.5, textColor=MUTED,
        ),
        "cite": ParagraphStyle(
            "cite", parent=base["Normal"], fontName="Helvetica", fontSize=8,
            leading=11, textColor=MUTED, spaceAfter=6,
        ),
    }


def _esc(text: str | None) -> str:
    if not text:
        return ""
    # Citation tags read [12] here, as on the site and in the source list, not [S12].
    text = re.sub(r"\[S(\d{1,3})\]", r"[\1]", str(text))
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bullets(items: list[str], style) -> ListFlowable:
    # Items saved before tag-only bullets were dropped at the source.
    items = [i for i in items if re.sub(r"\[S?\d{1,3}\]", "", str(i)).strip(" .;,:-")]
    return ListFlowable(
        [ListItem(Paragraph(_esc(i), style), leftIndent=10) for i in items],
        bulletType="bullet",
        bulletFontSize=6,
        bulletOffsetY=-1,
        leftIndent=12,
        spaceBefore=2,
    )


def _fmt_value(value, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "percent":
        return f"{value * 100:.1f}%"
    if unit == "x":
        return f"{value:.2f}x"
    if unit == "days":
        return f"{value:.0f}d"
    if unit == "currency":
        a = abs(value)
        for cut, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
            if a >= cut:
                return f"${value / cut:.2f}{suffix}"
        return f"${value:,.0f}"
    if unit == "score":
        return f"{value:.1f}"
    return f"{value:.2f}"


AREA_LABELS = {
    "profitability": "Profitability",
    "financial_health": "Financial health",
    "growth": "Growth",
    "valuation": "Valuation",
    "sentiment": "Sentiment",
}
SOURCE_LABELS = {
    "sec_10k": "Annual report",
    "sec_10q": "Quarterly report",
    "yf_news": "News",
    "rss": "Newswire",
}


def _score(value) -> str:
    """One decimal, truncated, as on the site: a 4.97 must not print as a Hold-looking
    "5.0" next to a Sell."""
    if value is None:
        return "—"
    return f"{int(float(value) * 10 + 1e-9) / 10:.1f}"


def _nice_date(value: str | None) -> str:
    """2026-09-25 -> 25 September 2026."""
    try:
        d = datetime.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return str(value or "")
    return f"{d.day} {d.strftime('%B %Y')}"


GRADE_COLOURS = {
    "Strong": colors.HexColor("#16774A"),
    "Average": colors.HexColor("#975F00"),
    "Weak": colors.HexColor("#B3261E"),
}


def _grade(score: float, buy: float, hold: float) -> str:
    """Same words and cut-offs as the report card on the site."""
    if score >= buy:
        return "Strong"
    if score >= hold:
        return "Average"
    return "Weak"


def _in_short(detail: dict) -> str | None:
    """The site's plain-English summary, assembled from the scorecard rather than the
    model, so it cannot disagree with the numbers. Mirrors components/in-short.tsx."""
    card = detail.get("scorecard") or {}
    if not card:
        return None
    market = (detail.get("blocks") or {}).get("market") or {}
    name = market.get("name") or detail.get("ticker", "")
    price = market.get("price")
    verdict = {"BUY": "a buy", "HOLD": "a hold", "SELL": "a sell"}.get(card.get("rating"), "")
    parts = [f"{name} scores {_score(card.get('total'))} out of 10, which makes it {verdict}."]
    scored = {k: v for k, v in (card.get("dimension_scores") or {}).items() if v is not None}
    if len(scored) > 1:
        best = max(scored, key=scored.get)
        worst = min(scored, key=scored.get)
        parts.append(
            f"Its strongest area is {AREA_LABELS.get(best, best).lower()} and its weakest "
            f"is {AREA_LABELS.get(worst, worst).lower()}."
        )
    pt = card.get("price_target") or {}
    low, high = pt.get("low"), pt.get("high")
    if pt.get("available") and low is not None and high is not None and price:
        span = f"${low:,.2f} to ${high:,.2f}"
        if price > high:
            parts.append(
                f"At ${price:,.2f} the shares look expensive: similar companies suggest "
                f"they are worth {span}."
            )
        elif price < low:
            parts.append(
                f"At ${price:,.2f} the shares look cheap: similar companies suggest they "
                f"are worth {span}."
            )
        else:
            parts.append(
                f"At ${price:,.2f} the shares look fairly priced compared with similar "
                f"companies."
            )
        # Same reconciliation as the site: price and rating pointing different ways.
        weak = [AREA_LABELS.get(k, k).lower() for k, v in sorted(scored.items(), key=lambda x: x[1]) if v < 5]
        strong = [
            AREA_LABELS.get(k, k).lower()
            for k, v in sorted(scored.items(), key=lambda x: -x[1])
            if v >= 7.5
        ]
        if price < low and card.get("rating") != "BUY" and weak:
            verb = "holds" if len(weak) == 1 else "hold"
            parts.append(
                f"Cheap shares alone do not make a buy: weak {_join_and(weak)} {verb} the "
                f"overall score down."
            )
        elif price > high and card.get("rating") == "BUY" and strong:
            verb = "is" if len(strong) == 1 else "are"
            parts.append(
                f"It still rates a buy because its {_join_and(strong)} {verb} strong "
                f"enough to outweigh the price."
            )
    return " ".join(parts)


def _join_and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def build_memo_pdf(detail: dict) -> bytes:
    """``detail`` is the same payload the API returns for GET /analyses/{id}."""
    memo = detail.get("memo") or {}
    card = detail.get("scorecard") or {}
    blocks = detail.get("blocks") or {}
    st = _styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"{detail.get('ticker', '')} analysis",
        author="Assay",
    )

    flow: list = []
    ticker = detail.get("ticker", "")
    rating = memo.get("recommendation") or card.get("rating") or "—"
    colour = RATING_COLOURS.get(rating, INK)

    company = ((blocks.get("market") or {}).get("name")) or ticker
    flow.append(Paragraph(f"{_esc(company)} ({_esc(ticker)})", st["title"]))
    flow.append(
        Paragraph(
            f"Analyzed on {_esc(_nice_date(memo.get('as_of') or datetime.utcnow().date().isoformat()))}. "
            f"Confidence: "
            f"{_esc((memo.get('conviction') or card.get('conviction') or '—').capitalize())}.",
            st["sub"],
        )
    )

    # --- rating block ------------------------------------------------------
    target = "Not available"
    if memo.get("price_target_low") and memo.get("price_target_high"):
        target = f"${memo['price_target_low']:,.2f} – ${memo['price_target_high']:,.2f}"

    rating_table = Table(
        [
            [
                Paragraph(
                    f'<font color="{colour.hexval()}" size="22"><b>{_esc(rating.capitalize())}</b></font>',
                    st["body"],
                ),
                Paragraph(
                    f'<font size="8" color="{MUTED.hexval()}">Overall score</font><br/>'
                    f'<font size="14">{_score(card.get("total"))} / 10</font>',
                    st["body"],
                ),
                Paragraph(
                    f'<font size="8" color="{MUTED.hexval()}">Fair value range</font><br/>'
                    f'<font size="12">{_esc(target)}</font>',
                    st["body"],
                ),
            ]
        ],
        colWidths=[45 * mm, 45 * mm, 80 * mm],
    )
    rating_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, colour),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
            ]
        )
    )
    flow.append(rating_table)
    flow.append(Spacer(1, 4))
    flow.append(
        Paragraph(
            "Fair value range: what one share would be worth if the market valued this "
            "company the way it values similar companies.",
            st["small"],
        )
    )
    flow.append(Spacer(1, 8))

    summary = _in_short(detail)
    if summary:
        flow.append(Paragraph("In short", st["h2"]))
        flow.append(Paragraph(_esc(summary), st["body"]))

    # --- thesis ------------------------------------------------------------
    if memo.get("thesis"):
        flow.append(Paragraph("The full picture", st["h2"]))
        flow.append(Paragraph(_esc(memo["thesis"]), st["body"]))

    for heading, key in (
        ("What is going well", "key_drivers"),
        ("What could go wrong", "key_risks"),
        ("What would change the rating", "what_would_change_our_mind"),
    ):
        items = memo.get(key) or []
        if items:
            flow.append(KeepTogether([Paragraph(heading, st["h2"]), _bullets(items, st["item"])]))

    # --- scorecard ---------------------------------------------------------
    scores = card.get("dimension_scores") or {}
    weights = card.get("weights_applied") or {}
    if scores:
        flow.append(Paragraph("Report card", st["h2"]))
        thresholds = card.get("thresholds") or {}
        buy, hold = thresholds.get("buy", 7.5), thresholds.get("hold", 5.0)
        rows = [["Area", "Score out of 10", "Grade", "Weight"]]
        for dim, value in scores.items():
            rows.append(
                [
                    AREA_LABELS.get(dim, dim.replace("_", " ").capitalize()),
                    _score(value),
                    "—" if value is None else _grade(value, buy, hold),
                    f"{weights.get(dim, 0) * 100:.0f}%" if dim in weights else "—",
                ]
            )
        rows.append(["Overall", _score(card.get("total")), "", "100%"])
        table = Table(rows, colWidths=[60 * mm, 32 * mm, 28 * mm, 25 * mm], hAlign="LEFT")
        grade_colours = [
            ("TEXTCOLOR", (2, i), (2, i), GRADE_COLOURS[row[2]])
            for i, row in enumerate(rows)
            if row[2] in GRADE_COLOURS
        ]
        table.setStyle(
            TableStyle(
                grade_colours + [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.5, RULE),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        flow.append(table)

    # --- metrics -----------------------------------------------------------
    for key, heading in (
        ("profitability", "Profitability"),
        ("liquidity", "Financial health"),
        ("growth", "Growth"),
        ("peers", "Valuation"),
    ):
        block = blocks.get(key)
        if not block:
            continue
        rows = [["Measure", "Value", "Better than peers"]]
        for m in (block.get("metrics") or {}).values():
            rows.append(
                [
                    m.get("label") or m.get("name", ""),
                    _fmt_value(m.get("value"), m.get("unit", "ratio")),
                    "—" if m.get("peer_percentile") is None else f"{m['peer_percentile'] * 100:.0f}%",
                ]
            )
        table = Table(rows, colWidths=[80 * mm, 45 * mm, 25 * mm], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFB")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ]
            )
        )
        flow.append(Paragraph(heading, st["h2"]))
        if block.get("narrative"):
            flow.append(Paragraph(_esc(block["narrative"]), st["body"]))
        flow.append(table)

    # --- caveats and sources ----------------------------------------------
    caveats = memo.get("data_caveats") or []
    dq_warnings = (detail.get("data_quality") or {}).get("warnings") or []
    if caveats or dq_warnings:
        flow.append(Paragraph("Things to keep in mind", st["h2"]))
        notes = [
            "Some written explanations could not be generated for this analysis, so "
            "shorter automatic text was used in places. Every number is unaffected."
            if c.startswith("Parts of this memo were not written by a model")
            else c
            for c in list(caveats) + list(dq_warnings)
        ]
        flow.append(_bullets(notes, st["item"]))

    evidence = detail.get("evidence") or []
    if evidence:
        flow.append(PageBreak())
        flow.append(Paragraph("Sources", st["h2"]))
        flow.append(
            Paragraph(
                "The numbers in brackets in the text, like [1], point to these passages. "
                "Figures are calculated from the company's reports and need no source tag.",
                st["small"],
            )
        )
        flow.append(Spacer(1, 6))
        for e in evidence:
            label = str(e.get("label") or "").lstrip("S")
            kind = SOURCE_LABELS.get(e.get("source_type") or "", e.get("source_type") or "")
            head = f"<b>[{_esc(label)}]</b> {_esc(kind)}"
            if e.get("section"):
                head += f" — {_esc(e['section'])}"
            if e.get("published"):
                head += f" — {_esc(e['published'])}"
            flow.append(Paragraph(head, st["cite"]))
            flow.append(Paragraph(_esc((e.get("text") or "")[:600]), st["small"]))
            if e.get("url"):
                flow.append(Paragraph(f'<font color="{ACCENT.hexval()}">{_esc(e["url"])}</font>', st["small"]))
            flow.append(Spacer(1, 7))

    flow.append(Spacer(1, 10))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=RULE))
    flow.append(Spacer(1, 5))
    flow.append(
        Paragraph(
            "Assay. Figures come from the company's official financial reports, "
            "and the rating follows the same fixed rules for every company. For "
            "information only; this is not investment advice.",
            st["small"],
        )
    )

    doc.build(flow)
    return buf.getvalue()
