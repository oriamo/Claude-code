#!/usr/bin/env python3
"""
Scrape every review from an ApartmentRatings property page.

ApartmentRatings paginates with ?page=N and renders reviews server-side, so a
plain HTTP walk gets the whole set. Two extraction strategies run in order:

  1. schema.org JSON-LD `Review` objects  (stable, preferred)
  2. HTML block parsing                   (fallback when JSON-LD is absent)

Usage
-----
    python scrape_apartmentratings.py \
        --url "https://www.apartmentratings.com/md/landover/the-villages-at-morgan-metro_301336406020785/" \
        --out reviews_apartmentratings.json
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from common import (
    UA, dedupe, find_reviews_in_jsonld, iter_jsonld, make_record, write_output,
)

SOURCE = "apartmentratings"


def from_jsonld(html: str, url: str) -> list[dict[str, Any]]:
    """Preferred path: pull structured Review objects straight out of the page."""
    records = []
    for blob in iter_jsonld(html):
        for review in find_reviews_in_jsonld(blob):
            rating = (review.get("reviewRating") or {}).get("ratingValue")
            author = review.get("author")
            if isinstance(author, dict):
                author = author.get("name")

            body = review.get("reviewBody") or review.get("description") or ""
            if not body.strip():
                continue

            records.append(
                make_record(
                    source=SOURCE,
                    review_id=str(
                        review.get("@id")
                        or review.get("identifier")
                        or abs(hash(body[:120]))
                    ),
                    text=body,
                    rating=rating,
                    raw_date=review.get("datePublished"),
                    author=author,
                    url=url,
                )
            )
    return records


def from_html(html: str, url: str) -> list[dict[str, Any]]:
    """Fallback: locate review blocks by class-name shape, not exact names.

    ApartmentRatings renames CSS classes periodically, so match on substrings
    ('review' in the class) rather than pinning an exact selector.
    """
    soup = BeautifulSoup(html, "lxml")
    records = []

    blocks = soup.find_all(
        ["article", "div", "li"],
        class_=lambda value: bool(value) and "review" in " ".join(
            value if isinstance(value, list) else [value]
        ).lower(),
    )

    for index, block in enumerate(blocks):
        text_node = block.find(
            ["p", "div", "span"],
            class_=lambda v: bool(v) and any(
                k in " ".join(v if isinstance(v, list) else [v]).lower()
                for k in ("body", "text", "content", "comment")
            ),
        )
        body = (text_node or block).get_text(" ", strip=True)
        if len(body.split()) < 5:
            continue

        rating = None
        rating_node = block.find(attrs={"class": re.compile(r"rating|star", re.I)})
        if rating_node:
            match = re.search(r"([0-5](?:\.\d)?)", rating_node.get_text(" ", strip=True))
            if match:
                rating = match.group(1)

        raw_date = None
        date_node = block.find(["time", "span", "div"], class_=re.compile(r"date", re.I))
        if date_node:
            raw_date = date_node.get("datetime") or date_node.get_text(" ", strip=True)

        records.append(
            make_record(
                source=SOURCE,
                review_id=f"{abs(hash(body[:120]))}-{index}",
                text=body,
                rating=rating,
                raw_date=raw_date,
                url=url,
            )
        )
    return records


def scrape(base_url: str, max_pages: int, delay: float) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

    base = base_url.split("?")[0].rstrip("/") + "/"
    all_records: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()

    for page in range(1, max_pages + 1):
        url = base if page == 1 else f"{base}?page={page}"
        resp = session.get(url, timeout=30)
        if resp.status_code == 404:
            break
        resp.raise_for_status()

        page_records = from_jsonld(resp.text, url) or from_html(resp.text, url)
        if not page_records:
            print(f"  page {page}: no reviews found, stopping", file=sys.stderr)
            break

        # Some sites clamp out-of-range pages back to page 1 instead of 404ing;
        # an all-duplicate page means we have already walked off the end.
        signature = "|".join(sorted(r["review_id"] for r in page_records))
        if signature in seen_signatures:
            print(f"  page {page}: duplicate of an earlier page, stopping", file=sys.stderr)
            break
        seen_signatures.add(signature)

        all_records.extend(page_records)
        print(f"  page {page}: +{len(page_records)} reviews", file=sys.stderr)
        time.sleep(delay)

    return dedupe(all_records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="ApartmentRatings property URL")
    parser.add_argument("--out", default="reviews_apartmentratings.json")
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    records = scrape(args.url, args.max_pages, args.delay)
    write_output(args.out, SOURCE, records, property_url=args.url)
    print(f"\nwrote {len(records)} reviews -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
