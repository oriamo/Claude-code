#!/usr/bin/env python3
"""
Scrape every review from a Yelp business page.

Yelp renders reviews client-side, so parsing the HTML shell gets you nothing.
This uses the same JSON feed the page itself calls:

    /biz/{slug}/review_feed?rl=en&sort_by=date_desc&start=N

Paginates in blocks of 10 until the feed runs dry.

Note that this property has TWO Yelp listings — the live one and a closed
Pinnacle/Cushwake-era listing carrying ~28 older reviews. Scrape both and merge;
the filter's date gate will drop whatever falls outside your window.

Usage
-----
    python scrape_yelp.py --slug villages-at-morgan-metro-landover-2 \
        --out reviews_yelp.json

    python scrape_yelp.py \
        --slug villages-at-morgan-metro-apartments-by-pinnacle-cushwake-landover \
        --out reviews_yelp_closed.json
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import requests

from common import UA, dedupe, make_record, write_output

SOURCE = "yelp"
FEED = "https://www.yelp.com/biz/{slug}/review_feed"


def extract(entry: dict[str, Any], slug: str) -> dict[str, Any] | None:
    """Map one feed entry onto the shared record schema."""
    comment = entry.get("comment") or {}
    body = comment.get("text") or ""
    if not body.strip():
        return None

    user = entry.get("user") or {}
    rating = entry.get("rating")

    # Yelp exposes an ISO timestamp on some payload shapes and a display date
    # on others; prefer the precise one.
    raw_date = (
        entry.get("localizedDate")
        or entry.get("timeCreated")
        or entry.get("localizedDateVisited")
    )

    owner_response = None
    for response in entry.get("businessOwnerReplies") or []:
        text = (response.get("comment") or {}).get("text")
        if text:
            owner_response = text
            break

    return make_record(
        source=SOURCE,
        review_id=str(entry.get("id") or abs(hash(body[:120]))),
        text=body,
        rating=rating,
        raw_date=raw_date,
        author=user.get("markupDisplayName") or user.get("displayName"),
        owner_response=owner_response,
        url=f"https://www.yelp.com/biz/{slug}",
    )


def scrape(slug: str, delay: float, max_pages: int) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            # The feed rejects requests that do not look like they came from
            # the business page itself.
            "Referer": f"https://www.yelp.com/biz/{slug}",
            "X-Requested-With": "XMLHttpRequest",
        }
    )

    records: list[dict[str, Any]] = []
    start = 0

    for page in range(max_pages):
        resp = session.get(
            FEED.format(slug=slug),
            params={"rl": "en", "sort_by": "date_desc", "start": start},
            timeout=30,
        )
        resp.raise_for_status()

        entries = resp.json().get("reviews") or []
        if not entries:
            break

        page_records = [r for r in (extract(e, slug) for e in entries) if r]
        records.extend(page_records)
        print(f"  start={start}: +{len(page_records)} reviews", file=sys.stderr)

        if len(entries) < 10:
            break
        start += 10
        time.sleep(delay)

    return dedupe(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True, help="Yelp business slug from the URL")
    parser.add_argument("--out", default="reviews_yelp.json")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--max-pages", type=int, default=60)
    args = parser.parse_args()

    records = scrape(args.slug, args.delay, args.max_pages)
    write_output(args.out, SOURCE, records, slug=args.slug)
    print(f"\nwrote {len(records)} reviews -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
