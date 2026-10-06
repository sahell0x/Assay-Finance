"""SEC EDGAR: the highest-signal source in the system.

Two things here are not optional.

**The User-Agent.** SEC returns 403 to any request without a descriptive User-Agent
carrying a contact address. It is configured, not hardcoded, because it has to be a real
address belonging to whoever is running the system. The 10 requests/second limit is
enforced client-side by :class:`_RateLimiter`.

**Streaming the parse.** A modern 10-K is 10-20 MB of HTML with inline XBRL. Building a
full lxml DOM over that routinely peaks around half a gigabyte, which is fatal on a 2 GB
box that is also running Postgres connections and a worker. So the document is consumed
as a byte stream, tags are stripped incrementally with a small state machine, and input
is capped at 8 MB — past which the interesting sections have always already appeared.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from dataclasses import dataclass

import httpx

from ...config import settings

log = logging.getLogger(__name__)

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
TICKER_MAP = "https://www.sec.gov/files/company_tickers.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

# Tags whose boundaries are paragraph breaks in the rendered document. Preserving them
# is what lets the risk-factor splitter find headers later.
BLOCK_TAGS = re.compile(
    rb"</?(?:p|div|br|tr|table|h[1-6]|li|ul|ol|section|article)\b[^>]*>", re.IGNORECASE
)
SKIP_BLOCKS = re.compile(rb"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)


class _RateLimiter:
    """SEC allows 10 requests/second. Exceeding it earns a block, not a 429."""

    def __init__(self, per_second: int = 8) -> None:
        self._interval = 1.0 / per_second
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            gap = now - self._last
            if gap < self._interval:
                await asyncio.sleep(self._interval - gap)
            self._last = time.monotonic()


_limiter = _RateLimiter()


def headers() -> dict[str, str]:
    ua = settings.sec_user_agent.strip().strip('"')
    if "@" not in ua:
        log.warning(
            "SEC_USER_AGENT has no contact address; EDGAR will reject these requests"
        )
    return {
        "User-Agent": ua,
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov",
    }


@dataclass
class Filing:
    form: str            # "10-K" | "10-Q"
    accession: str
    filing_date: str
    report_date: str
    primary_doc: str
    url: str
    cik: int


# ------------------------------------------------------------------------- discovery


_ticker_cik: dict[str, int] | None = None


async def ticker_to_cik(ticker: str, client: httpx.AsyncClient | None = None) -> int | None:
    """Resolve a ticker to its CIK using SEC's own mapping file."""
    global _ticker_cik
    if _ticker_cik is None:
        own = client is None
        client = client or httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        try:
            await _limiter.wait()
            resp = await client.get(TICKER_MAP, headers=headers())
            resp.raise_for_status()
            data = resp.json()
            _ticker_cik = {
                str(row["ticker"]).upper(): int(row["cik_str"]) for row in data.values()
            }
        except Exception as exc:
            log.warning("could not load the SEC ticker map: %s", exc)
            _ticker_cik = {}
        finally:
            if own:
                await client.aclose()
    return _ticker_cik.get(ticker.upper())


async def recent_filings(
    ticker: str, forms: tuple[str, ...] = ("10-K", "10-Q"), limit_per_form: int = 1
) -> list[Filing]:
    """The most recent filing of each requested form."""
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        cik = await ticker_to_cik(ticker, client)
        if cik is None:
            log.info("%s has no CIK in the SEC mapping (likely a foreign issuer or ETF)", ticker)
            return []

        await _limiter.wait()
        headers_ = dict(headers(), Host="data.sec.gov")
        try:
            resp = await client.get(SUBMISSIONS.format(cik=cik), headers=headers_)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            log.warning("EDGAR submissions fetch failed for %s: %s", ticker, exc)
            return []

    recent = (payload.get("filings") or {}).get("recent") or {}
    rows = zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("filingDate", []),
        recent.get("reportDate", []),
        recent.get("primaryDocument", []),
        strict=False,
    )

    found: dict[str, list[Filing]] = {f: [] for f in forms}
    for form, accession, filed, report, doc in rows:
        if form not in found or len(found[form]) >= limit_per_form:
            continue
        if not doc:
            continue
        clean = accession.replace("-", "")
        found[form].append(
            Filing(
                form=form,
                accession=accession,
                filing_date=filed,
                report_date=report or filed,
                primary_doc=doc,
                url=ARCHIVE.format(cik=cik, accession=clean, document=doc),
                cik=cik,
            )
        )
        if all(len(v) >= limit_per_form for v in found.values()):
            break

    return [f for group in found.values() for f in group]


# ----------------------------------------------------------------------- streaming


def strip_tags(raw: bytes) -> str:
    """Turn a chunk of filing HTML into text, preserving paragraph structure.

    Regex rather than a parser, deliberately: this runs over multi-megabyte documents
    and must not allocate a tree.
    """
    raw = SKIP_BLOCKS.sub(b" ", raw)
    raw = BLOCK_TAGS.sub(b"\n", raw)
    raw = re.sub(rb"<[^>]{0,4000}>", b" ", raw)
    text = raw.decode("utf-8", errors="replace")
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


async def fetch_document_text(url: str, max_bytes: int | None = None) -> str:
    """Download and de-tag a filing without ever holding the whole DOM.

    Bytes arrive in chunks; each is de-tagged as it lands and only the (far smaller)
    text is retained. A partial tag straddling a chunk boundary is carried forward so it
    is not mangled.
    """
    max_bytes = max_bytes or settings.edgar_max_bytes
    out: list[str] = []
    carry = b""
    total = 0
    truncated = False

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
        await _limiter.wait()
        async with client.stream("GET", url, headers=headers()) as resp:
            resp.raise_for_status()
            async for raw in resp.aiter_bytes(chunk_size=256 * 1024):
                total += len(raw)
                buf = carry + raw

                # Hold back anything after the last complete '>' so a tag split across
                # the boundary is not treated as text.
                cut = buf.rfind(b">")
                if cut == -1 or len(buf) - cut > 64 * 1024:
                    cut = len(buf) - 1
                carry = buf[cut + 1 :]
                out.append(strip_tags(buf[: cut + 1]))

                if total >= max_bytes:
                    truncated = True
                    break

    if carry:
        out.append(strip_tags(carry))

    text = "".join(out)
    if truncated:
        log.info("filing at %s truncated at %d bytes", url, max_bytes)
    return re.sub(r"\n{3,}", "\n\n", text)


# ------------------------------------------------------------------ section extraction

# "Item 1A." with the flexible whitespace and punctuation real filings use.
def _item_pattern(item: str, *, words: str) -> re.Pattern[str]:
    return re.compile(
        rf"item\s*{item}\s*[.:\-—]?\s*{words}", re.IGNORECASE
    )


ITEM_1A = _item_pattern("1A", words=r"risk\s+factors")
ITEM_1B = _item_pattern("1B", words=r"unresolved\s+staff\s+comments")
ITEM_2_PROPERTIES = _item_pattern("2", words=r"properties")
ITEM_7 = _item_pattern(
    "7", words=r"management[’'`s\s]*\s*discussion\s+and\s+analysis"
)
ITEM_7A = _item_pattern("7A", words=r"quantitative\s+and\s+qualitative")
ITEM_8 = _item_pattern("8", words=r"financial\s+statements")


def extract_section(
    text: str, start: re.Pattern[str], ends: list[re.Pattern[str]], *, min_length: int = 800
) -> str | None:
    """Slice out one numbered Item.

    The *last* match of the start pattern is used. The first match is almost always the
    table of contents entry, and slicing from there yields the table of contents rather
    than the section — the single most common way filing extraction goes wrong.
    """
    starts = list(start.finditer(text))
    if not starts:
        return None

    for match in reversed(starts):
        begin = match.end()
        stop = len(text)
        for end_pat in ends:
            m = end_pat.search(text, begin)
            if m and m.start() < stop:
                stop = m.start()
        body = text[begin:stop].strip()
        if len(body) >= min_length:
            return body

    # Every candidate was too short — fall back to the longest slice available rather
    # than discarding the section entirely.
    match = starts[-1]
    body = text[match.end() :].strip()
    return body if len(body) >= min_length else None


def extract_risk_factors(text: str) -> str | None:
    return extract_section(text, ITEM_1A, [ITEM_1B, ITEM_2_PROPERTIES])


def extract_mdna(text: str) -> str | None:
    return extract_section(text, ITEM_7, [ITEM_7A, ITEM_8])


async def fetch_sections(ticker: str) -> list[dict]:
    """The latest 10-K and 10-Q, reduced to Item 1A and Item 7.

    Never raises: an unreachable EDGAR degrades the analysis to news-only rather than
    failing it.
    """
    out: list[dict] = []
    try:
        filings = await recent_filings(ticker)
    except Exception as exc:
        log.warning("EDGAR discovery failed for %s: %s", ticker, exc)
        return out

    for filing in filings:
        try:
            text = await fetch_document_text(filing.url)
        except Exception as exc:
            log.warning("could not fetch %s %s: %s", ticker, filing.form, exc)
            continue

        source_type = "sec_10k" if filing.form == "10-K" else "sec_10q"
        for label, extractor in (
            ("Item 1A. Risk Factors", extract_risk_factors),
            ("Item 7. Management's Discussion and Analysis", extract_mdna),
        ):
            body = extractor(text)
            if not body:
                continue
            out.append(
                {
                    "source_type": source_type,
                    "section": label,
                    "title": f"{ticker} {filing.form} filed {filing.filing_date}",
                    "url": filing.url,
                    "published": filing.filing_date,
                    "text": body,
                    "is_risk_factors": label.startswith("Item 1A"),
                }
            )
    return out
