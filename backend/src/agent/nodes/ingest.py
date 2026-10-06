"""Node 1 of the pipeline: fetch and normalise everything downstream needs.

This is the only node that is not optional. If the statements cannot be sourced there is
no analysis to do, and the run fails loudly rather than producing a confident memo about
a company it knows nothing about.
"""

from __future__ import annotations

from ...data.fundamentals import get_fundamentals
from ..progress import node


@node("ingest")
async def ingest(state: dict) -> dict:
    ticker = state["ticker"].upper()
    f = await get_fundamentals(ticker)

    if not f.periods:
        raise ValueError(
            f"No financial statements are available for {ticker}. The symbol may be "
            f"delisted, an index, or unsupported by the data provider."
        )

    warnings = list(f.data_quality.get("warnings", []))
    return {
        "facts": f.to_dict(),
        "market": f.market,
        "data_quality": f.data_quality,
        "warnings": warnings,
    }
