#!/usr/bin/env python3
"""
Filter a scraped review set down to *residents, last N years* — and show its work.

Two gates, applied in order:

  1. RECENCY  — drop anything older than the cutoff (default 3 years).
  2. TENANCY  — drop reviews written by people who never lived there: tour-only
     visitors, applicants, and prospects whose entire review is about the
     leasing office experience before move-in.

The tenancy gate is deliberately conservative. A review is only dropped when it
shows prospect signals AND no lived-there signals, so genuine resident reviews
that happen to praise the leasing agent survive. Everything ambiguous is routed
to a `needs_review` bucket for a human rather than being silently discarded.

Accepts any number of scraper outputs and merges them, so Google,
ApartmentRatings and Yelp go through one identical set of gates.

Usage
-----
    python filter_reviews.py reviews_*.json --years 3 --out filtered.json
    python filter_reviews.py reviews_google.json --print-kept
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

# --- Signals that the writer actually lived in a unit -------------------------
RESIDENT_PATTERNS = [
    r"\b(i|we)('ve| have)? (lived|been living|stayed|resided)\b",
    r"\bmov(ed|ing) (in|out)\b",
    r"\bmy (apartment|unit|apt|townhome|home|neighbou?rs?|building|lease)\b",
    r"\b(my|our) (rent|landlord|water bill|kitchen|bathroom|bedroom|balcony|patio)\b",
    r"\b(lease renewal|renewed my lease|maintenance request|work order)\b",
    r"\b(year|years|month|months) (here|living here|at this)\b",
    r"\b(current|former|ex)[- ]?(resident|tenant)\b",
    r"\b(resident|tenant) (here|of|for)\b",
    r"\bsince i moved\b",
    r"\b(mice|roaches|rodents?|infestation|leak|mold|a\/?c|heat) (in|under|behind)? ?(my|our|the) ?(apartment|unit|home|kitchen|wall)",
]

# --- Signals that the writer was only shopping / touring ---------------------
PROSPECT_PATTERNS = [
    r"\b(toured|took a tour|went for a tour|on my tour|showed me (the|around)|walk[- ]?through)\b",
    r"\b(looking|searching|shopping) for (an? )?(apartment|place|home)\b",
    r"\b(applied|application|applying) (for|to|process)\b",
    r"\b(considering|thinking about|hoping to|planning to|about to) (mov|rent|appl|leas)",
    r"\b(prospective|future|soon[- ]to[- ]be) (resident|tenant)\b",
    r"\bcan'?t wait to move in\b",
    r"\b(called|phoned|stopped by|visited) the (leasing )?office\b",
    r"\b(leasing (agent|consultant|office|staff)|front desk) (was|were|is|are)\b",
    r"\bmade the (process|experience) (so )?easy\b",
    r"\bhelped me (find|with my application|through the process)\b",
]

# --- Stadium / event traffic topic tag ---------------------------------------
STADIUM_PATTERNS = [
    r"\b(fedex ?field|northwest stadium|the stadium|commanders|redskins)\b",
    r"\b(game ?day|game days|football game|home game|concert|event)s?\b",
    r"\b(tailgat|traffic|gridlock|road clos|blocked in|can'?t get (in|out))\w*",
]

RESIDENT_RE = [re.compile(p, re.I) for p in RESIDENT_PATTERNS]
PROSPECT_RE = [re.compile(p, re.I) for p in PROSPECT_PATTERNS]
STADIUM_RE = [re.compile(p, re.I) for p in STADIUM_PATTERNS]


def matches(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    """Return the actual substrings that matched, so decisions stay auditable."""
    hits = []
    for pattern in patterns:
        found = pattern.search(text)
        if found:
            hits.append(found.group(0).strip())
    return hits


def review_date(review: dict[str, Any]) -> date | None:
    """Resolve a record's date, tolerating the older pre-schema field names."""
    for field in ("date", "approx_date"):
        value = review.get(field)
        if value:
            try:
                return date.fromisoformat(value)
            except (ValueError, TypeError):
                continue

    micros = review.get("timestamp_us")
    if isinstance(micros, (int, float)) and micros > 0:
        return datetime.fromtimestamp(micros / 1_000_000, tz=timezone.utc).date()
    return None


def load_reviews(paths: list[str]) -> list[dict[str, Any]]:
    """Merge every scraper output into one list, de-duplicated by review id."""
    merged: list[dict[str, Any]] = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)

        records = payload["reviews"] if isinstance(payload, dict) else payload
        source = payload.get("source", "unknown") if isinstance(payload, dict) else "unknown"
        for record in records:
            record.setdefault("source", source)
        merged.extend(records)
        print(f"loaded {len(records):>4} from {path}", file=sys.stderr)

    seen: set[str] = set()
    unique = []
    for record in merged:
        key = record.get("review_id") or f"anon:{abs(hash(record.get('text', '')[:120]))}"
        if key not in seen:
            seen.add(key)
            unique.append(record)

    if len(unique) != len(merged):
        print(f"dropped {len(merged) - len(unique)} duplicate ids", file=sys.stderr)
    return unique


def classify(review: dict[str, Any], cutoff: date) -> dict[str, Any]:
    """Tag one review with a verdict and the evidence behind it."""
    text = (review.get("text") or "").strip()
    when = review_date(review)

    resident_hits = matches(text, RESIDENT_RE)
    prospect_hits = matches(text, PROSPECT_RE)

    result = {
        **review,
        "resolved_date": when.isoformat() if when else None,
        "resident_signals": resident_hits,
        "prospect_signals": prospect_hits,
        "stadium_signals": matches(text, STADIUM_RE),
    }

    # Gate 1: recency.
    if when is None:
        result["verdict"] = "needs_review"
        result["reason"] = "no usable date"
        return result
    if when < cutoff:
        result["verdict"] = "excluded_old"
        result["reason"] = f"dated {when.isoformat()}, before cutoff {cutoff.isoformat()}"
        return result

    # Gate 2: tenancy.
    if not text:
        result["verdict"] = "excluded_no_text"
        result["reason"] = "rating only, no text to assess tenancy"
        return result

    if resident_hits:
        result["verdict"] = "kept"
        result["reason"] = "resident language present"
    elif prospect_hits:
        result["verdict"] = "excluded_non_resident"
        result["reason"] = "prospect/leasing-office language, no lived-there signal"
    elif len(text.split()) < 12:
        result["verdict"] = "needs_review"
        result["reason"] = "too short to classify confidently"
    else:
        result["verdict"] = "kept"
        result["reason"] = "substantive review, no prospect-only signal"

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("infiles", nargs="+", help="One or more scraper outputs")
    parser.add_argument("--years", type=float, default=3.0)
    parser.add_argument("--out", default="reviews_filtered.json")
    parser.add_argument("--print-kept", action="store_true")
    args = parser.parse_args()

    reviews = load_reviews(args.infiles)
    cutoff = date.today() - timedelta(days=365.25 * args.years)

    classified = [classify(r, cutoff) for r in reviews]

    buckets: dict[str, list[dict[str, Any]]] = {}
    for review in classified:
        buckets.setdefault(review["verdict"], []).append(review)

    kept = buckets.get("kept", [])
    stadium = [r for r in kept if r["stadium_signals"]]

    total = len(classified)
    print(f"\n{'=' * 58}")
    print("REVIEW FILTER AUDIT")
    print(f"{'=' * 58}")
    print(f"cutoff date            : {cutoff.isoformat()} ({args.years} years)")
    print(f"total reviews accessed : {total}")
    print(f"{'-' * 58}")
    for verdict in (
        "excluded_old", "excluded_non_resident", "excluded_no_text", "needs_review"
    ):
        count = len(buckets.get(verdict, []))
        share = f"{count / total * 100:5.1f}%" if total else "  n/a"
        print(f"  {verdict:<24}: {count:>4}  {share}")
    filtered_out = total - len(kept)
    print(f"{'-' * 58}")
    print(f"total filtered out     : {filtered_out}")
    print(f"REMAINING (kept)       : {len(kept)}")
    print(f"  ...mentioning stadium/event traffic: {len(stadium)}")

    sources = sorted({r.get("source", "unknown") for r in classified})
    if len(sources) > 1:
        print(f"{'-' * 58}")
        print(f"  {'source':<20}{'accessed':>10}{'filtered':>10}{'kept':>8}")
        for name in sources:
            got = [r for r in classified if r.get("source") == name]
            held = [r for r in got if r["verdict"] == "kept"]
            print(f"  {name:<20}{len(got):>10}{len(got) - len(held):>10}{len(held):>8}")

    if kept:
        rated = [r["rating"] for r in kept if isinstance(r.get("rating"), (int, float))]
        if rated:
            print(f"  mean rating of kept set : {sum(rated) / len(rated):.2f}")
            spread = {star: rated.count(star) for star in range(1, 6)}
            print(f"  distribution            : {spread}")
    print(f"{'=' * 58}\n")

    if args.print_kept:
        for review in sorted(kept, key=lambda r: r["resolved_date"] or "", reverse=True):
            print(f"[{review['resolved_date']}] {review['rating']}* "
                  f"{review.get('author') or 'anon'} ({review.get('source', '?')})")
            print(f"  {review['text'][:600]}\n")

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "cutoff": cutoff.isoformat(),
                "counts": {
                    "accessed": total,
                    "filtered_out": filtered_out,
                    "remaining": len(kept),
                    "by_verdict": {k: len(v) for k, v in buckets.items()},
                    "stadium_mentions": len(stadium),
                },
                "kept": kept,
                "excluded": [r for r in classified if r["verdict"] != "kept"],
            },
            handle, indent=2, ensure_ascii=False,
        )
    print(f"wrote -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
