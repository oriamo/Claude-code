# Morgan Metro review census

Tooling to pull the **complete** Google review list for The Villages at Morgan Metro
(8251 Ridgefield Blvd, Landover, MD 20785) and filter it down to *residents, last 3 years*.

## Why this is a script and not a finished dataset

This tooling was written inside a sandboxed session whose egress proxy blocks
**all** outbound hosts except package registries — `google.com`, `apartmentratings.com`,
`apartments.com`, `yelp.com` and every other review source return `403` at the gateway,
bypassing the proxy included. So the scrape could not be executed here. Run it from an
unrestricted machine and it will produce the counts directly.

## Install

```bash
pip install requests
```

## Run

```bash
# 1. Pull every Google review, newest first
python scrape_google_reviews.py \
    --url "https://maps.app.goo.gl/4YapY447cE8UuaF8A" \
    --out reviews_google.json

# 2. Filter to residents, last 3 years, with a full audit trail
python filter_reviews.py reviews_google.json --years 3 --print-kept
```

`filter_reviews.py` prints exactly the three numbers you want — total accessed,
total filtered out (broken down by reason), and total remaining — plus a count of
how many surviving reviews mention stadium/event traffic.

## How the filters work

**Recency gate.** Uses the exact review timestamp when Google supplies one, falling
back to the resolved relative date ("3 months ago"). Anything with no usable date goes
to `needs_review` rather than being dropped.

**Tenancy gate.** A review is only excluded as non-resident when it shows prospect
signals (toured, applied, "can't wait to move in", leasing-office-only praise) **and**
no lived-there signals ("my unit", "maintenance request", "since I moved in", "lived
here two years"). That asymmetry matters: a resident who praises the leasing agent is
kept, while a tour-only visitor who does the same is dropped. Short or ambiguous
reviews land in `needs_review` for a human instead of being silently discarded.

Every verdict records the substrings that triggered it, so you can audit any decision
in the output JSON rather than trusting the classifier blind.

## Extending to other sources

Google is the largest single pool but not the only one. ApartmentRatings (~114 reviews),
Apartments.com, Yelp (two listings — the live one and a closed Pinnacle/Cushwake
listing), VeryApt (6), and ForRent (~172 ratings) all carry reviews. `filter_reviews.py`
accepts any JSON list whose records expose `text`, `rating`, and either `timestamp_us`
or `approx_date`, so point a scraper at those and reuse the same gates.
