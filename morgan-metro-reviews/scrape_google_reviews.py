#!/usr/bin/env python3
"""
Pull the COMPLETE Google Maps review list for a place.

The public Places API caps you at 5 reviews. This uses the same internal
endpoint the Maps web UI calls (`/maps/rpc/listugcposts`), which paginates
through every review a place has.

Usage
-----
    # Resolve a place and dump every review to JSON
    python scrape_google_reviews.py \
        --url "https://maps.app.goo.gl/4YapY447cE8UuaF8A" \
        --out reviews_google.json

    # Or skip resolution if you already have the feature ID
    python scrape_google_reviews.py --feature-id "0x89b7:0x1234" --out out.json

Notes
-----
* Sorted newest-first, so you can stop early once you pass your date cutoff.
* Google returns relative dates ("3 months ago"). We resolve them to an
  approximate absolute date against the scrape timestamp and keep the raw
  string so nothing is silently lost.
* Be polite: the default 1.5s delay between pages exists for a reason.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Iterator

import requests

from common import UA, dedupe, make_record, write_output

SOURCE = "google"

# Sort orders accepted by the endpoint.
SORT = {"relevance": 1, "newest": 2, "highest": 3, "lowest": 4}

FEATURE_ID_RE = re.compile(r"0x[0-9a-f]+:0x[0-9a-f]+")


def resolve_feature_id(url: str, session: requests.Session) -> str:
    """Follow a Maps URL (short links included) and scrape out the feature ID."""
    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    # The hex CID shows up in the page payload and often in the final URL.
    for haystack in (resp.url, resp.text):
        match = FEATURE_ID_RE.search(haystack)
        if match:
            return match.group(0)

    raise RuntimeError(
        "Could not find a feature ID (0x…:0x…) for that URL. "
        "Open the place in Maps, copy the full /maps/place/… URL, and pass that."
    )


def build_pb(feature_id: str, page_token: str, sort: int, page_size: int) -> str:
    """Assemble the protobuf-ish query string the endpoint expects."""
    return (
        f"!1m6!1s{feature_id}!6m4!4m1!1e1!4m1!1e3"
        f"!2m2!1i{page_size}!2s{page_token}"
        f"!5m2!1sanything!7e81"
        f"!8m9!2b1!3b1!5b1!7b1!12m4!1b1!2b1!4m1!1e1"
        f"!11m6!1e3!2e1!3sen!4s{feature_id}!6m1!1i2"
        f"!13m1!1e{sort}"
    )


def parse_response(raw: str) -> tuple[list[Any], str | None]:
    """Strip the anti-JSON-hijack prefix and pull out (entries, next_token)."""
    payload = json.loads(raw[raw.index("\n") + 1:])
    entries = payload[2] or []
    next_token = payload[1].strip('"') if payload[1] else None
    return entries, next_token


def _dig(obj: Any, *path: int, default: Any = None) -> Any:
    """Index into deeply nested lists without a pyramid of try/except."""
    for key in path:
        try:
            obj = obj[key]
        except (IndexError, KeyError, TypeError):
            return default
    return obj if obj is not None else default


def extract_review(entry: Any) -> dict[str, Any]:
    """Map one raw entry onto the shared record schema."""
    micros = _dig(entry, 0, 1, 5, 0)
    relative = _dig(entry, 0, 1, 6)

    # An exact timestamp beats Google's relative label whenever it is present.
    raw_date = relative
    if isinstance(micros, (int, float)) and micros > 0:
        raw_date = datetime.fromtimestamp(
            micros / 1_000_000, tz=timezone.utc
        ).date().isoformat()

    record = make_record(
        source=SOURCE,
        review_id=str(_dig(entry, 0, 0)),
        text=_dig(entry, 0, 2, 15, 0, 0) or "",
        rating=_dig(entry, 0, 2, 0, 0),
        raw_date=raw_date,
        author=_dig(entry, 0, 1, 4, 5, 0),
        owner_response=_dig(entry, 0, 3, 14, 0, 0),
    )
    record.update(
        {
            "relative_date": relative,
            "local_guide": bool(_dig(entry, 0, 1, 4, 5, 10)),
            "photo_count": len(_dig(entry, 0, 2, 2, default=[]) or []),
        }
    )
    return record


def iter_reviews(
    feature_id: str,
    session: requests.Session,
    sort: str = "newest",
    page_size: int = 20,
    delay: float = 1.5,
    max_pages: int = 500,
) -> Iterator[dict[str, Any]]:
    """Yield every review, walking the pagination cursor to exhaustion."""
    token, pages = "", 0

    while pages < max_pages:
        params = {
            "authuser": "0", "hl": "en", "gl": "us",
            "pb": build_pb(feature_id, token, SORT[sort], page_size),
        }
        resp = session.get(
            "https://www.google.com/maps/rpc/listugcposts", params=params, timeout=30
        )
        resp.raise_for_status()

        entries, token = parse_response(resp.text)
        if not entries:
            break

        for entry in entries:
            yield extract_review(entry)

        pages += 1
        print(f"  page {pages}: +{len(entries)} reviews", file=sys.stderr)

        if not token:
            break
        time.sleep(delay)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Any Google Maps URL for the place")
    source.add_argument("--feature-id", help="Known feature ID (0x…:0x…)")
    parser.add_argument("--out", default="reviews_google.json")
    parser.add_argument("--sort", choices=SORT, default="newest")
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

    feature_id = args.feature_id or resolve_feature_id(args.url, session)
    print(f"feature id: {feature_id}", file=sys.stderr)

    reviews = list(
        iter_reviews(
            feature_id, session,
            sort=args.sort, page_size=args.page_size, delay=args.delay,
        )
    )

    # The endpoint can repeat entries across page boundaries.
    unique = dedupe(reviews)
    write_output(args.out, SOURCE, unique, feature_id=feature_id)

    print(f"\nwrote {len(unique)} unique reviews -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
