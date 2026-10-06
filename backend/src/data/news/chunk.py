"""Chunking.

1000 characters with 180 of overlap, split on paragraph boundaries in preference to
sentence boundaries in preference to hard character counts.

Risk factors get special handling. In a 10-K, Item 1A is a list of named risks with
bolded headers, and each one is a self-contained claim — "Our business depends on a
small number of suppliers", then four paragraphs about it. Splitting on those headers
means a retrieval hit returns one whole risk instead of the tail of one and the head of
the next, which is the difference between a citable chunk and a confusing one.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

CHUNK_SIZE = 1000
OVERLAP = 180
MIN_CHUNK = 120

PARAGRAPH = re.compile(r"\n\s*\n")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# A risk-factor header: a short line in title or sentence case, often ending without a
# full stop, sometimes numbered. Conservative on purpose — a false positive fragments a
# risk, which is worse than missing a split.
RISK_HEADER = re.compile(
    r"^(?:•\s*)?(?:\d{1,2}[.)]\s+)?"
    r"((?:[A-Z][^.!?\n]{25,180}?)(?:\.|\:)?)\s*$",
    re.MULTILINE,
)


@dataclass
class Chunk:
    text: str
    ticker: str
    source_type: str
    section: str | None = None
    title: str | None = None
    url: str | None = None
    published: str | None = None
    chunk_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.chunk_id:
            self.chunk_id = make_chunk_id(
                self.ticker, self.source_type, self.section, self.url, self.text
            )

    def as_row(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "ticker": self.ticker,
            "source_type": self.source_type,
            "section": self.section,
            "title": self.title,
            "url": self.url,
            "published": self.published,
            "text": self.text,
        }


def make_chunk_id(
    ticker: str, source_type: str, section: str | None, url: str | None, text: str
) -> str:
    """Content-addressed, so re-indexing the same filing is idempotent."""
    digest = hashlib.sha256(
        f"{ticker}|{source_type}|{section or ''}|{url or ''}|{text}".encode()
    ).hexdigest()[:24]
    return f"{ticker.lower()}-{source_type}-{digest}"


def normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pack(units: list[str], size: int, overlap: int) -> list[str]:
    """Greedily fill chunks from pre-split units, carrying an overlap tail forward."""
    chunks: list[str] = []
    current = ""

    for unit in units:
        unit = unit.strip()
        if not unit:
            continue
        if not current:
            current = unit
        elif len(current) + 1 + len(unit) <= size:
            current = f"{current}\n\n{unit}" if "\n" in unit or len(unit) > 200 else f"{current} {unit}"
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap and len(current) > overlap else ""
            # Start the overlap at a word boundary so a chunk never opens mid-word.
            if tail:
                space = tail.find(" ")
                tail = tail[space + 1 :] if space != -1 else ""
            current = f"{tail} {unit}".strip() if tail else unit

        while len(current) > size * 1.6:
            # A single oversized unit (a table, a run-on paragraph) still has to be cut.
            cut = _hard_cut(current, size)
            chunks.append(current[:cut].strip())
            current = current[max(cut - overlap, 0) :].strip()

    if current:
        chunks.append(current)
    return [c for c in chunks if len(c) >= MIN_CHUNK]


def _hard_cut(text: str, size: int) -> int:
    window = text[:size]
    for sep in (". ", "; ", ", ", " "):
        idx = window.rfind(sep)
        if idx > size * 0.5:
            return idx + len(sep)
    return size


def chunk_text(
    text: str,
    *,
    ticker: str,
    source_type: str,
    section: str | None = None,
    title: str | None = None,
    url: str | None = None,
    published: str | None = None,
    size: int = CHUNK_SIZE,
    overlap: int = OVERLAP,
) -> list[Chunk]:
    text = normalise(text)
    if not text:
        return []

    paragraphs = [p for p in PARAGRAPH.split(text) if p.strip()]
    units: list[str] = []
    for p in paragraphs:
        if len(p) <= size:
            units.append(p)
        else:
            units.extend(SENTENCE.split(p))

    return [
        Chunk(
            text=body,
            ticker=ticker,
            source_type=source_type,
            section=section,
            title=title,
            url=url,
            published=published,
        )
        for body in _pack(units, size, overlap)
    ]


def split_risk_factors(text: str) -> list[tuple[str, str]]:
    """Split Item 1A into ``(header, body)`` pairs, one per named risk.

    Falls back to returning the whole section as a single unnamed unit when no headers
    are detectable, which is what happens with filings that run risk factors as
    continuous prose.
    """
    text = normalise(text)
    lines = text.split("\n")

    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not (25 <= len(stripped) <= 200):
            continue
        if stripped.endswith((".", ":")) and len(stripped) > 160:
            continue
        if not stripped[:1].isupper():
            continue
        # A header stands alone: a blank line (or the start of the section) precedes it,
        # and there is body prose somewhere after it. Filings vary on whether a blank
        # line separates the header from its body, so only the preceding gap is required.
        prev_blank = i == 0 or not lines[i - 1].strip()
        has_body_after = any(line.strip() for line in lines[i + 1 :])
        words = stripped.split()
        if prev_blank and has_body_after and len(words) >= 4 and not stripped.endswith(","):
            starts.append((i, stripped.rstrip(".:")))

    if len(starts) < 3:
        return [("", text)]

    out: list[tuple[str, str]] = []
    for idx, (line_no, header) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        body = "\n".join(lines[line_no + 1 : end]).strip()
        if len(body) >= MIN_CHUNK:
            out.append((header, body))
    return out or [("", text)]


def chunk_risk_factors(
    text: str,
    *,
    ticker: str,
    source_type: str,
    url: str | None = None,
    published: str | None = None,
    title: str | None = None,
) -> list[Chunk]:
    """One chunk per named risk where possible, sub-chunked when a risk runs long."""
    chunks: list[Chunk] = []
    for header, body in split_risk_factors(text):
        section = f"Item 1A. Risk Factors — {header}" if header else "Item 1A. Risk Factors"
        combined = f"{header}\n\n{body}" if header else body
        if len(combined) <= CHUNK_SIZE * 1.3:
            chunks.append(
                Chunk(
                    text=combined.strip(),
                    ticker=ticker,
                    source_type=source_type,
                    section=section,
                    title=title,
                    url=url,
                    published=published,
                )
            )
        else:
            parts = chunk_text(
                combined, ticker=ticker, source_type=source_type, section=section,
                title=title, url=url, published=published,
            )
            chunks.extend(parts)
    return chunks
