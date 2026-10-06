"""Embeddings.

512 dimensions, requested via the API's ``dimensions`` parameter rather than by slicing
a 1536-vector. That matters: the model produces a natively 512-dimensional, correctly
normalised vector, so cosine distance stays meaningful. A truncated-and-not-renormalised
slice would not.

The pairing with ``halfvec`` is what keeps the index inside a free-tier storage budget —
512 half-precision values is 1 KB per row against 6 KB for fp32 at 1536.

Which endpoint serves these is a separate question from which one serves chat: the
router's embeddings client comes from ``EMBEDDING_*``, because a gateway that proxies
chat completions often does not proxy embeddings. Nothing here needs to know — it asks
the router and the router picks.
"""

from __future__ import annotations

import asyncio
import logging

from ...agent.models import Usage, failure_reason, get_router
from ...config import settings


class EmbeddingError(RuntimeError):
    """Raised when the embeddings endpoint cannot be reached or refuses the request.

    Carries a reason that names the setting to change, because "APIConnectionError"
    tells the person running `seed_index.py` nothing about which of four environment
    variables is wrong.
    """

log = logging.getLogger(__name__)

BATCH = 96  # well inside the API's per-request limits, few enough to retry cheaply


async def embed_texts(texts: list[str], usage: Usage | None = None) -> list[list[float]]:
    """Embed in batches, preserving order."""
    if not texts:
        return []
    router = get_router()
    out: list[list[float]] = []

    for i in range(0, len(texts), BATCH):
        batch = [t.replace("\n", " ")[:8000] for t in texts[i : i + BATCH]]
        for attempt in range(3):
            try:
                out.extend(await router.embed(batch, usage))
                break
            except Exception as exc:
                if attempt == 2:
                    # Raising is right — a caller asking to index cannot be given a
                    # half-built corpus — but the exception a provider throws says
                    # nothing about which setting is wrong. Re-raise with the reason
                    # named, so `seed_index.py` prints something actionable rather than
                    # a transport error.
                    reason = failure_reason(exc, settings.embedding_model)
                    raise EmbeddingError(
                        f"Embeddings are unavailable: {reason}"
                    ) from exc
                wait = 2**attempt
                log.warning("embedding batch failed (%s); retrying in %ss", exc, wait)
                await asyncio.sleep(wait)
    return out


async def embed_query(text: str, usage: Usage | None = None) -> list[float]:
    vectors = await embed_texts([text], usage)
    if not vectors:
        raise RuntimeError("embedding the query returned nothing")
    return vectors[0]


def dims() -> int:
    return settings.embedding_dims
