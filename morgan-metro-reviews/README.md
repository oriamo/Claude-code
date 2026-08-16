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
pip install requests beautifulsoup4 lxml
```

## Run

```bash
# 1. Google — the full list, newest first
python scrape_google_reviews.py \
    --url "https://maps.app.goo.gl/4YapY447cE8UuaF8A" \
    --out reviews_google.json

# 2. ApartmentRatings — walks ?page=N to exhaustion
python scrape_apartmentratings.py \
    --url "https://www.apartmentratings.com/md/landover/the-villages-at-morgan-metro_301336406020785/" \
    --out reviews_apartmentratings.json

# 3. Yelp — note this property has TWO listings, scrape both
python scrape_yelp.py --slug villages-at-morgan-metro-landover-2 \
    --out reviews_yelp.json
python scrape_yelp.py \
    --slug villages-at-morgan-metro-apartments-by-pinnacle-cushwake-landover \
    --out reviews_yelp_closed.json

# 4. One filter over everything, with a full audit trail
python filter_reviews.py reviews_*.json --years 3 --print-kept
```

`filter_reviews.py` prints exactly the three numbers you want — total accessed,
total filtered out (broken down by reason), and total remaining — plus a per-source
table and a count of how many surviving reviews mention stadium/event traffic.

## Architecture

`common.py` defines one flat record schema that every scraper emits, so the filter
never special-cases a source:

| field | notes |
|---|---|
| `source` | `google` / `apartmentratings` / `yelp` |
| `review_id` | namespaced by source, so merges can't collide |
| `rating` | normalised to a 1–5 scale via `scale=` |
| `date` + `date_precision` | `exact` when the site printed a real date, `approx` when resolved from "3 months ago" |
| `raw_date` | whatever the site actually printed, kept for auditing |

Adding a fourth source (Apartments.com, ForRent, VeryApt) means writing a scraper
that calls `make_record()` and `write_output()`. The filter picks it up with no changes.

### Per-source extraction notes

**Google** calls the internal `listugcposts` endpoint — the same one the Maps UI
uses. This is what gets you the *full* list; the official Places API caps at 5 reviews.

**ApartmentRatings** tries schema.org JSON-LD first and falls back to HTML block
parsing. The fallback matches on class-name *substrings* rather than exact selectors,
because the site renames its CSS periodically. It also stops when a page repeats an
earlier page's contents, since out-of-range pages there clamp back to page 1 rather
than 404.

**Yelp** renders reviews client-side, so the HTML shell is useless — this hits the
`review_feed` JSON endpoint the page itself calls, which requires a `Referer` header
pointing at the business page.

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

## Known review pools

| Source | Pool size | Published rating | Covered here |
|---|---|---|---|
| Google | unknown | — | yes |
| ApartmentRatings | 113–114 | 3.1 / 5 | yes |
| Yelp (live listing) | small | — | yes |
| Yelp (closed Pinnacle/Cushwake listing) | ~28 | — | yes |
| ForRent | ~172 | 4.2 / 5 | not yet |
| VeryApt | 6 | 6.5 "Good" | not yet |

The ForRent 4.2 against ApartmentRatings 3.1 on the same property is worth noting:
syndicated feeds tend to carry a high share of leasing-office reviews, which is exactly
what the tenancy gate strips out.

## Caveat on testing

The parsing, date-resolution, merge and filter logic are all exercised against fixtures.
The **network paths were never executed** because of the egress block described above, so
validate each scraper's first live run before trusting its counts — particularly the
ApartmentRatings HTML fallback and the Yelp feed shape, which are the two most likely to
have drifted.
