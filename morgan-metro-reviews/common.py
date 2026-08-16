"""
Shared record schema and helpers for every review scraper in this package.

All scrapers emit the same flat record so `filter_reviews.py` can consume any
mix of sources without special-casing:

    {
      "source":         "google" | "apartmentratings" | "yelp",
      "review_id":      str,
      "author":         str | None,
      "rating":         float | None,      # normalised to a 1-5 scale
      "date":           "YYYY-MM-DD" | None,
      "date_precision": "exact" | "approx" | None,
      "raw_date":       str | None,        # whatever the site actually printed
      "text":           str,
      "owner_response": str | None,
      "url":            str | None,
    }
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_RELATIVE_RE = re.compile(
    r"(a|an|\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", re.I
)

_UNIT_DAYS = {
    "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30.44, "year": 365.25,
}

# Formats these sites actually print, most specific first.
_DATE_FORMATS = (
    "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%d %b %Y", "%B %Y", "%b %Y",
)


def parse_relative_date(text: str, now: datetime | None = None) -> str | None:
    """'3 months ago' -> approximate ISO date."""
    if not text:
        return None
    match = _RELATIVE_RE.search(text)
    if not match:
        return None

    now = now or datetime.now(timezone.utc)
    count = 1 if match.group(1).lower() in ("a", "an") else int(match.group(1))
    days = _UNIT_DAYS[match.group(2).lower()] * count
    return (now - timedelta(days=days)).date().isoformat()


def parse_absolute_date(text: str) -> str | None:
    """Parse the printed date formats these sites use, into ISO."""
    if not text:
        return None
    cleaned = text.strip().replace("Reviewed on", "").strip(" ,")

    # An embedded ISO timestamp beats any locale format guessing.
    iso = re.search(r"\d{4}-\d{2}-\d{2}", cleaned)
    if iso:
        return iso.group(0)

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def resolve_date(raw: str) -> tuple[str | None, str | None]:
    """Return (iso_date, precision) from whatever a site printed."""
    exact = parse_absolute_date(raw)
    if exact:
        return exact, "exact"
    approx = parse_relative_date(raw)
    if approx:
        return approx, "approx"
    return None, None


def make_record(
    source: str,
    review_id: str,
    text: str,
    rating: Any = None,
    raw_date: str | None = None,
    author: str | None = None,
    owner_response: str | None = None,
    url: str | None = None,
    scale: float = 5.0,
) -> dict[str, Any]:
    """Build one normalised record, rescaling the rating to 1-5 if needed."""
    iso, precision = resolve_date(raw_date or "")

    score = None
    if rating is not None:
        try:
            score = round(float(rating) * (5.0 / scale), 2)
        except (TypeError, ValueError):
            score = None

    return {
        "source": source,
        "review_id": f"{source}:{review_id}",
        "author": author,
        "rating": score,
        "date": iso,
        "date_precision": precision,
        "raw_date": raw_date,
        "text": (text or "").strip(),
        "owner_response": owner_response,
        "url": url,
    }


def dedupe(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeats that paginated endpoints hand back across boundaries."""
    return list({r["review_id"]: r for r in records}.values())


def write_output(path: str, source: str, records: list[dict[str, Any]], **extra: Any) -> None:
    payload = {
        "source": source,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "total_scraped": len(records),
        **extra,
        "reviews": records,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def iter_jsonld(html: str) -> Iterable[Any]:
    """Yield every JSON-LD blob in a page, tolerating the malformed ones."""
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.S | re.I,
    ):
        try:
            yield json.loads(block.strip())
        except json.JSONDecodeError:
            continue


def find_reviews_in_jsonld(node: Any) -> list[dict[str, Any]]:
    """Walk a JSON-LD tree collecting every schema.org Review object."""
    found: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, dict):
            node_type = item.get("@type", "")
            types = node_type if isinstance(node_type, list) else [node_type]
            if "Review" in types:
                found.append(item)
            for value in item.values():
                if isinstance(value, (dict, list)):
                    walk(value)

    walk(node)
    return found
