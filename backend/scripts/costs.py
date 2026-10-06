#!/usr/bin/env python
"""What a run costs, and what changing the model routing would do to it.

    python scripts/costs.py                  # current config, measured from your own runs
    python scripts/costs.py --compare        # every preset side by side
    python scripts/costs.py --runs 50        # widen the sample

The token profile is taken from analyses already in your database, so the figures
describe this deployment rather than a guess. With no completed runs it falls back to a
measured profile from a representative large-cap analysis.

The memo dominates. It is the only call that receives all four metric blocks plus the
full evidence set, and on the default routing it is ~47% of the tokens but ~84% of the
spend, because the top tier costs 12x the input and 25x the output of the cheap one.
That makes MODEL_MEMO the one setting worth thinking about.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.core.budget import PRICING, estimate_cost, price_for  # noqa: E402
from src.db.session import SessionLocal, dispose_engine  # noqa: E402

ROLES = ("narrative", "rag", "memo", "critic")

# Measured from a completed large-cap analysis: (prompt tokens, completion tokens).
# Used only when the database has nothing to sample.
FALLBACK_PROFILE: dict[str, tuple[int, int]] = {
    "memo": (5386, 200),
    "critic": (2999, 120),
    "rag": (2302, 120),
    "narrative": (798, 270),
}

# Routings worth comparing. The names describe the trade, not a product tier.
PRESETS: dict[str, dict[str, str]] = {
    "economy": {
        "narrative": "gpt-5.6-luna",
        "rag": "gpt-5.6-luna",
        "memo": "gpt-5.6-terra",
        "critic": "gpt-5.6-luna",
    },
    "balanced": {
        "narrative": "gpt-5.6-luna",
        "rag": "gpt-5.6-terra",
        "memo": "gpt-5.6-terra",
        "critic": "gpt-5.6-luna",
    },
    "quality": {
        "narrative": "gpt-5.6-luna",
        "rag": "gpt-5.6-terra",
        "memo": "gpt-5.6-sol",
        "critic": "gpt-5.6-luna",
    },
}


def current_config() -> dict[str, str]:
    return {
        "narrative": settings.model_narrative,
        "rag": settings.model_rag,
        "memo": settings.model_memo,
        "critic": settings.model_critic,
    }


async def measured_profile(limit: int) -> tuple[dict[str, tuple[int, int]], int]:
    """Average tokens per role across recent completed runs."""
    from sqlalchemy import desc, select

    from src.db.models import Analysis

    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    runs = 0
    try:
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(Analysis.blocks)
                    .where(Analysis.status == "complete", Analysis.blocks.isnot(None))
                    .order_by(desc(Analysis.completed_at))
                    .limit(limit)
                )
            ).scalars().all()
    except Exception:
        return FALLBACK_PROFILE, 0

    for blocks in rows:
        calls = ((blocks or {}).get("cost") or {}).get("calls") or []
        if not calls:
            continue
        runs += 1
        for call in calls:
            role = _role_of(call.get("label", ""))
            totals[role][0] += int(call.get("tokens_in", 0))
            totals[role][1] += int(call.get("tokens_out", 0))

    if not runs:
        return FALLBACK_PROFILE, 0
    return {r: (v[0] // runs, v[1] // runs) for r, v in totals.items()}, runs


def _role_of(label: str) -> str:
    head = label.split(":")[0].split(" ")[0].strip()
    if head.startswith("narrative"):
        return "narrative"
    if head in {"sentiment"}:
        return "rag"
    if head.startswith("memo"):
        return "memo"
    if head.startswith("critic"):
        return "critic"
    if head.startswith("embed"):
        return "embedding"
    return head or "other"


def cost_of(config: dict[str, str], profile: dict[str, tuple[int, int]]) -> float:
    return sum(
        estimate_cost(config.get(role, ""), tin, tout)
        for role, (tin, tout) in profile.items()
        if role in config
    )


def render_breakdown(config: dict[str, str], profile: dict[str, tuple[int, int]]) -> None:
    total = cost_of(config, profile)
    print(f"  {'role':<11}{'model':<18}{'$/M in':>8}{'$/M out':>9}{'tokens':>14}{'cost':>10}{'share':>8}")
    print("  " + "-" * 76)
    rows = [
        (role, config[role], estimate_cost(config[role], *profile[role]), profile[role])
        for role in ROLES
        if role in config and role in profile
    ]
    for role, model, cost, (tin, tout) in sorted(rows, key=lambda r: -r[2]):
        pin, pout = price_for(model)
        known = "" if model in PRICING else " *"
        share = (cost / total * 100) if total else 0
        print(
            f"  {role:<11}{model[:17]:<18}{pin:>8.2f}{pout:>9.2f}"
            f"{tin:>8,}/{tout:<5,}{cost:>10.5f}{share:>7.0f}%{known}"
        )
    print("  " + "-" * 76)
    print(f"  {'per analysis':<46}{total:>22.5f}")
    print(f"  {'per 1,000 analyses':<46}{'$' + format(total * 1000, ',.2f'):>22}")
    cap = float(settings.daily_cap_usd)
    if total > 0:
        print(f"  {'runs before the $' + format(cap, '.2f') + ' daily cap':<46}{int(cap / total):>22,}")
    if any(m not in PRICING for m in config.values()):
        print("\n  * price unknown to src/core/budget.py; the mid tier was assumed.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="show every preset")
    parser.add_argument("--runs", type=int, default=20, help="how many recent runs to sample")
    args = parser.parse_args()

    try:
        profile, sampled = await measured_profile(args.runs)
        source = (
            f"averaged over your {sampled} most recent completed run(s)"
            if sampled
            else "a measured large-cap run (no completed analyses in this database yet)"
        )

        print("\nToken profile —", source)
        print()
        config = current_config()
        print("Current configuration")
        render_breakdown(config, profile)

        if args.compare:
            print("\n\nPresets")
            print(f"  {'preset':<12}{'memo model':<18}{'cost/run':>12}{'per 1,000':>13}{'vs quality':>13}")
            print("  " + "-" * 68)
            quality = cost_of(PRESETS["quality"], profile)
            for name in ("economy", "balanced", "quality"):
                c = cost_of(PRESETS[name], profile)
                delta = f"{(c / quality - 1) * 100:+.0f}%" if quality else "—"
                print(
                    f"  {name:<12}{PRESETS[name]['memo']:<18}{c:>12.5f}"
                    f"{'$' + format(c * 1000, ',.2f'):>13}{delta:>13}"
                )
            print()
            print("  The memo is the only lever that matters: it is the single call that")
            print("  receives all four metric blocks plus the full evidence set. Moving it")
            print("  from the top tier to the middle one is the whole saving; the other")
            print("  three roles together are under a fifth of the bill.")
            print()
            print("  Set MODEL_MEMO in backend/.env to change it. Nothing else needs to move.")

        return 0
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
